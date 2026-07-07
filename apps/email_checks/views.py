from celery.result import AsyncResult
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_checks.models import EmailCheckRequest
from apps.email_checks.serializers import EmailCheckRunSerializer
from apps.email_checks.tasks import run_outlook_check_task


class OutlookEmailCheckRunView(APIView):
    def post(self, request):
        serializer = EmailCheckRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        email_check_request = EmailCheckRequest.objects.create(
            email=data['email'],
            password=data['password'],
            status='queued',
            max_messages=data['max_messages'],
            user=request.user if request.user.is_authenticated else None,
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
                'task_id': task.id,
                'status_url': request.build_absolute_uri(
                    reverse('email-check-task-status', kwargs={'task_id': task.id})
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class OutlookEmailCheckTaskStatusView(APIView):
    def get(self, request, task_id):
        task = AsyncResult(task_id)
        response_data = {
            'task_id': task_id,
            'state': task.state,
        }

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

        return Response(response_data, status=status.HTTP_200_OK)
