from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.email_checks.models import EmailCheckRequest
from apps.email_checks.services import run_outlook_check


def _update_email_check_request(request_id: int | None, **fields) -> None:
    if request_id is None:
        return

    EmailCheckRequest.objects.filter(id=request_id).update(**fields)


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
        raise self.retry(
            exc=exc,
            countdown=settings.CELERY_EMAIL_CHECK_RETRY_DELAY_SECONDS,
            max_retries=settings.CELERY_EMAIL_CHECK_RETRY_COUNT,
        )

    _update_email_check_request(
        request_id,
        status=result.get('status', 'success'),
        otp=result.get('otp') or '',
        total_try=self.request.retries,
        error_message='',
        finish_at=timezone.now(),
    )
    return result
