import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib import request
from urllib.error import URLError

from django.conf import settings

from apps.email_checks.models import EmailCheckRequest, Webhook
from apps.email_checks.responses import webhook_result_payload

logger = logging.getLogger(__name__)


@dataclass
class UserNotification:
    webhook: Webhook
    timeout: int = settings.EMAIL_CHECK_WEBHOOK_TIMEOUT_SECONDS

    def send_email_check_result(
        self,
        email_check_request: EmailCheckRequest,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error_message: str = '',
    ) -> None:
        payload = webhook_result_payload(
            email_check_request,
            status=status,
            result=result,
            error_message=error_message,
        )
        self.send(payload)

    def send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if self.webhook.header_key:
            headers[self.webhook.header_key] = self.webhook.header_value

        webhook_request = request.Request(
            self.webhook.webhook,
            data=body,
            headers=headers,
            method='POST',
        )

        try:
            with request.urlopen(webhook_request, timeout=self.timeout) as response:
                response.read()
        except (OSError, URLError) as exc:
            logger.warning(
                'Failed to send email check result webhook: request_id=%s webhook_id=%s url=%s error=%s',
                payload.get('request_id'),
                self.webhook.id,
                self.webhook.webhook,
                exc,
            )
