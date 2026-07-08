from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.email_checks.models import EmailCheckRequest
from apps.email_checks.notifications import UserNotification
from apps.email_checks.services import run_outlook_check
from apps.scraper.exceptions import LoginFailed


def _update_email_check_request(request_id: int | None, **fields) -> None:
    if request_id is None:
        return

    EmailCheckRequest.objects.filter(id=request_id).update(**fields)


def _notify_email_check_request(
    request_id: int | None,
    *,
    status: str,
    result: dict | None = None,
    error_message: str = '',
) -> None:
    if request_id is None:
        return

    email_check_request = (
        EmailCheckRequest.objects
        .select_related('webhook')
        .filter(id=request_id)
        .first()
    )
    if email_check_request is None or email_check_request.webhook is None:
        return

    UserNotification(email_check_request.webhook).send_email_check_result(
        email_check_request,
        status=status,
        result=result,
        error_message=error_message,
    )


@shared_task(
    bind=True,
    name='email_checks.run_outlook_check',
    max_retries=settings.CELERY_EMAIL_CHECK_RETRY_COUNT,
)
def run_outlook_check_task(
    self,
    *,
    email: str,
    password: str,
    max_messages: int,
    headless: bool | None = None,
    request_id: int | None = None,
) -> dict:
    _update_email_check_request(
        request_id,
        status='started',
        start_at=timezone.now(),
        total_try=self.request.retries,
        error_message='',
    )

    try:
        result = run_outlook_check(
            email=email,
            password=password,
            max_messages=max_messages,
            headless=headless,
        )
    except LoginFailed as exc:
        _update_email_check_request(
            request_id,
            status='failed',
            total_try=self.request.retries,
            error_message=str(exc),
            finish_at=timezone.now(),
        )
        _notify_email_check_request(
            request_id,
            status='failed',
            error_message=str(exc),
        )
        raise
    except Exception as exc:
        total_try = min(self.request.retries + 1, settings.CELERY_EMAIL_CHECK_RETRY_COUNT)
        retry_status = 'retrying'
        if self.request.retries >= settings.CELERY_EMAIL_CHECK_RETRY_COUNT:
            retry_status = 'failed'

        _update_email_check_request(
            request_id,
            status=retry_status,
            total_try=total_try,
            error_message=str(exc),
            finish_at=timezone.now() if retry_status == 'failed' else None,
        )
        if retry_status == 'failed':
            _notify_email_check_request(
                request_id,
                status='failed',
                error_message=str(exc),
            )
        raise self.retry(
            exc=exc,
            countdown=settings.CELERY_EMAIL_CHECK_RETRY_DELAY_SECONDS,
            max_retries=settings.CELERY_EMAIL_CHECK_RETRY_COUNT,
        )

    final_status = result.get('status', 'success')
    _update_email_check_request(
        request_id,
        status=final_status,
        otp=result.get('otp') or '',
        total_try=self.request.retries,
        error_message='',
        finish_at=timezone.now(),
    )
    _notify_email_check_request(
        request_id,
        status=final_status,
        result=result,
    )
    return result
