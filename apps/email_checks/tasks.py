from celery import shared_task

from apps.email_checks.services import run_outlook_check


@shared_task(name='email_checks.run_outlook_check')
def run_outlook_check_task(*, email: str, password: str, max_messages: int) -> dict:
    return run_outlook_check(
        email=email,
        password=password,
        max_messages=max_messages,
    )
