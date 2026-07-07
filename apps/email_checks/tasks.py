from celery import shared_task
from django.conf import settings

from apps.email_checks.services import run_outlook_check


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
    headless: bool = True,
) -> dict:
    try:
        return run_outlook_check(
            email=email,
            password=password,
            max_messages=max_messages,
            headless=headless,
        )
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=settings.CELERY_EMAIL_CHECK_RETRY_DELAY_SECONDS,
            max_retries=settings.CELERY_EMAIL_CHECK_RETRY_COUNT,
        )
