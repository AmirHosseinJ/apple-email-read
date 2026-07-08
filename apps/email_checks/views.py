from celery.result import AsyncResult
from django.shortcuts import get_object_or_404
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_checks.models import EmailCheckRequest, Webhook
from apps.email_checks.notifications import UserNotification
from apps.email_checks.responses import create_request_payload, error_payload, progress_payload
from apps.email_checks.serializers import EmailCheckRunSerializer, WebhookQuerySerializer
from apps.email_checks.tasks import run_outlook_check_task


def get_request_ip(request):
    return request.META.get('REMOTE_ADDR') or ''


class OutlookEmailCheckRunView(APIView):
    def post(self, request):
        serializer = EmailCheckRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        webhook = Webhook.objects.filter(ip=get_request_ip(request)).first()
        if webhook is None:
            return Response(
                create_request_payload(
                    ok=False,
                    status='webhook_not_configured',
                    error=error_payload(
                        'WEBHOOK_NOT_CONFIGURED',
                        'No webhook is configured for this request source IP.',
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        email_check_request = EmailCheckRequest.objects.create(
            email=data['email'],
            password=data['password'],
            status='queued',
            max_messages=data['max_messages'],
            user=request.user if request.user.is_authenticated else None,
            webhook=webhook,
        )

        try:
            task = run_outlook_check_task.delay(
                email=data['email'],
                password=data['password'],
                max_messages=data['max_messages'],
                request_id=email_check_request.id,
            )
        except OperationalError as exc:
            email_check_request.status = 'queue_failed'
            email_check_request.error_message = str(exc)
            email_check_request.finish_at = timezone.now()
            email_check_request.save(update_fields=['status', 'error_message', 'finish_at', 'updated_at'])
            UserNotification(webhook).send_email_check_result(
                email_check_request,
                status='queue_failed',
                error_message=str(exc),
            )
            return Response(
                create_request_payload(
                    ok=False,
                    status='queue_failed',
                    message=f'Failed to queue email check task: {exc}',
                    email_check_request=email_check_request,
                    error=error_payload('QUEUE_FAILED', str(exc)),
                ),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        email_check_request.task_id = task.id
        email_check_request.save(update_fields=['task_id', 'updated_at'])

        return Response(
            create_request_payload(
                ok=True,
                status='queued',
                email_check_request=email_check_request,
            ),
            status=status.HTTP_202_ACCEPTED,
        )


class OutlookEmailCheckRequestStatusView(APIView):
    def get(self, request, request_id):
        email_check_request = get_object_or_404(EmailCheckRequest, id=request_id)

        if not email_check_request.task_id:
            response_data = progress_payload(
                email_check_request,
                status=email_check_request.status,
                state=email_check_request.status.upper(),
                error_message=email_check_request.error_message,
            )
            return Response(response_data, status=status.HTTP_200_OK)

        task = AsyncResult(email_check_request.task_id)

        if task.successful():
            response_data = progress_payload(
                email_check_request,
                status='success',
                state=task.state,
                result=task.result,
            )
        elif task.failed():
            response_data = progress_payload(
                email_check_request,
                status='failure',
                state=task.state,
                error_message=str(task.result),
            )
        else:
            response_data = progress_payload(
                email_check_request,
                status=task.state.lower(),
                state=task.state,
            )

        return Response(response_data, status=status.HTTP_200_OK)


class AutomationWebhookView(APIView):
    def get(self, request):
        serializer = WebhookQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        ip = get_request_ip(request)
        if not ip:
            return Response(
                {'detail': 'Unable to determine request source IP.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        webhook, created = Webhook.objects.update_or_create(
            ip=ip,
            defaults=serializer.validated_data,
        )

        return Response(
            {
                'status': 'created' if created else 'updated',
                'id': webhook.id,
                'ip': webhook.ip,
                'webhook': webhook.webhook,
                'header_key': webhook.header_key,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
