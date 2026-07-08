from typing import Any

from apps.email_checks.models import EmailCheckRequest


FAILURE_STATUSES = {'failed', 'failure', 'queue_failed', 'webhook_not_configured'}
FINISHED_STATUSES = {'failed', 'failure', 'queue_failed', 'success', 'otp_found', 'otp_not_found'}


def queue_status_for_email_check_status(status: str) -> str:
    if status == 'queued':
        return 'PENDING'
    if status in {'started', 'pending'}:
        return 'STARTED'
    if status == 'retrying':
        return 'RETRY'
    if status in {'failed', 'failure', 'queue_failed', 'webhook_not_configured'}:
        return 'FAILURE'
    if status in {'success', 'otp_found', 'otp_not_found'}:
        return 'SUCCESS'
    return status.upper()


def task_retries(email_check_request: EmailCheckRequest) -> int:
    return email_check_request.total_try


def task_attempts(
    email_check_request: EmailCheckRequest,
    result: dict[str, Any] | None = None,
    *,
    status: str | None = None,
) -> int:
    if result and 'attempts' in result:
        return result['attempts']
    current_status = status or email_check_request.status
    if current_status in {'queued', 'pending'} and email_check_request.total_try == 0:
        return 0
    return email_check_request.total_try + 1


def task_message(status: str, error_message: str = '') -> str:
    messages = {
        'queued': 'Request accepted.',
        'started': 'Task is running.',
        'pending': 'Task is waiting to run.',
        'retrying': 'Task is retrying.',
        'success': 'Task completed.',
        'otp_found': 'Task completed.',
        'otp_not_found': 'Task completed, but no OTP was found.',
        'failed': 'Task failed.',
        'failure': 'Task failed.',
        'queue_failed': 'Failed to queue email check task.',
        'webhook_not_configured': 'No webhook is configured for this request source IP.',
    }
    return error_message or messages.get(status, 'Task status updated.')


def retry_meta(
    email_check_request: EmailCheckRequest | None,
    result: dict[str, Any] | None = None,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    if email_check_request is None:
        return {
            'attempts': 0,
            'retries': 0,
        }
    return {
        'attempts': task_attempts(email_check_request, result, status=status),
        'retries': task_retries(email_check_request),
    }


def error_payload(code: str, details: str = '') -> dict[str, str]:
    payload = {'code': code}
    if details:
        payload['details'] = details
    return payload


def create_request_payload(
    *,
    ok: bool,
    status: str,
    message: str | None = None,
    email_check_request: EmailCheckRequest | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        'ok': ok,
        'request_id': email_check_request.id if email_check_request else None,
        'queue_status': queue_status_for_email_check_status(status),
        'email_check_status': status,
        'message': message or task_message(status),
    }
    if not ok:
        payload['otp'] = email_check_request.otp if email_check_request and email_check_request.otp else None
        payload['error'] = error or error_payload(status.upper(), payload['message'])
        if payload['error'].get('details'):
            payload['detail'] = payload['error']['details']
    payload['meta'] = retry_meta(email_check_request, status=status)
    return payload


def progress_payload(
    email_check_request: EmailCheckRequest,
    *,
    status: str,
    state: str,
    result: dict[str, Any] | None = None,
    error_message: str = '',
) -> dict[str, Any]:
    finished = status in FINISHED_STATUSES
    payload = {
        'ok': status not in FAILURE_STATUSES,
        'request_id': email_check_request.id,
        'queue_status': state,
        'email_check_status': (result or {}).get('status') or status,
        'message': task_message(status, error_message),
    }
    if finished:
        payload['otp'] = email_check_request.otp or (result or {}).get('otp') or None
    if error_message:
        payload['detail'] = error_message
        payload['error'] = error_payload(status.upper(), error_message)
    payload['meta'] = retry_meta(email_check_request, result, status=status)
    return payload


def webhook_result_payload(
    email_check_request: EmailCheckRequest,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_message: str = '',
) -> dict[str, Any]:
    payload = {
        'ok': status not in FAILURE_STATUSES,
        'request_id': email_check_request.id,
        'email': email_check_request.email,
        'email_check_status': status,
        'message': task_message(status, error_message),
        'otp': email_check_request.otp or (result or {}).get('otp') or None,
        'error_message': error_message,
    }
    if error_message:
        payload['error'] = error_payload(status.upper(), error_message)
    payload['meta'] = retry_meta(email_check_request, result, status=status)
    return payload
