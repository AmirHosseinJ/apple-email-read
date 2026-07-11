from django.conf import settings


def otp_retry_count() -> int:
    return settings.OUTLOOK_OTP_RETRY_COUNT


def otp_retry_wait_seconds() -> int:
    return settings.OUTLOOK_OTP_RETRY_WAIT_SECONDS


def otp_attempt_timeout_seconds() -> int:
    return settings.OUTLOOK_OTP_ATTEMPT_TIMEOUT_SECONDS


def browser_headless() -> bool:
    return settings.EMAIL_CHECKS_HEADLESS


def browser_proxy() -> dict | None:
    if not settings.USE_PROXY or not settings.PROXY_SERVER:
        return None

    proxy = {'server': settings.PROXY_SERVER}
    if settings.PROXY_USERNAME:
        proxy['username'] = settings.PROXY_USERNAME
    if settings.PROXY_PASSWORD:
        proxy['password'] = settings.PROXY_PASSWORD

    return proxy
