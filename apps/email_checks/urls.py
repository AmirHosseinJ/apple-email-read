from django.urls import path

from apps.email_checks.views import OutlookEmailCheckRunView, OutlookEmailCheckTaskStatusView


urlpatterns = [
    path('email-checks/run/', OutlookEmailCheckRunView.as_view(), name='email-check-run'),
    path(
        'email-checks/tasks/<str:task_id>/',
        OutlookEmailCheckTaskStatusView.as_view(),
        name='email-check-task-status',
    ),
]
