from celery.result import AsyncResult
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_checks.models import EmailCheckRequest, Webhook
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
                {
                    'status': 'webhook_not_configured',
                    'detail': 'No webhook is configured for this request source IP.',
                },
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
            return Response(
                {'detail': f'Failed to queue email check task: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        email_check_request.task_id = task.id
        email_check_request.save(update_fields=['task_id', 'updated_at'])

        return Response(
            {
                'status': 'queued',
                'request_id': email_check_request.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class OutlookEmailCheckRequestStatusView(APIView):
    def get(self, request, request_id):
        email_check_request = get_object_or_404(EmailCheckRequest, id=request_id)
        total_retries = email_check_request.total_try
        meta = {
            'total_retries': total_retries,
            'remaining_tries': max(settings.CELERY_EMAIL_CHECK_RETRY_COUNT - total_retries, 0),
        }
        response_data = {
            'request_id': email_check_request.id,
        }

        if not email_check_request.task_id:
            response_data.update(
                {
                    'status': email_check_request.status,
                    'state': email_check_request.status.upper(),
                }
            )
            if email_check_request.error_message:
                response_data['detail'] = email_check_request.error_message
            response_data['meta'] = meta
            return Response(response_data, status=status.HTTP_200_OK)

        task = AsyncResult(email_check_request.task_id)
        response_data['state'] = task.state

        if task.successful():
            response_data.update(
                {
                    'status': 'success',
                    'result': task.result,
                }
            )
        elif task.failed():
            response_data.update(
                {
                    'status': 'failure',
                    'detail': str(task.result),
                }
            )
        else:
            response_data['status'] = task.state.lower()

        response_data['meta'] = meta
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
