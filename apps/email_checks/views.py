from celery.result import AsyncResult
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_checks.serializers import EmailCheckRunSerializer
from apps.email_checks.tasks import run_outlook_check_task


class OutlookEmailCheckRunView(APIView):
    def post(self, request):
        serializer = EmailCheckRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            task = run_outlook_check_task.delay(
                email=data['email'],
                password=data['password'],
                max_messages=data['max_messages'],
            )
        except OperationalError as exc:
            return Response(
                {'detail': f'Failed to queue email check task: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                'status': 'queued',
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
