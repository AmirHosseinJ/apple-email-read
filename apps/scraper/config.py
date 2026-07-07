from django.conf import settings


def otp_retry_count() -> int:
    return settings.OUTLOOK_OTP_RETRY_COUNT


def otp_retry_wait_seconds() -> int:
    return settings.OUTLOOK_OTP_RETRY_WAIT_SECONDS
