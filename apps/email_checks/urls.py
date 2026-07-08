from django.urls import path

from apps.email_checks.views import (
    AutomationWebhookView,
    OutlookEmailCheckRequestStatusView,
    OutlookEmailCheckRunView,
)


urlpatterns = [
    path('automation/webhook', AutomationWebhookView.as_view(), name='automation-webhook'),
    path('email-checks/run/', OutlookEmailCheckRunView.as_view(), name='email-check-run'),
    path(
        'email-checks/requests/<int:request_id>/',
        OutlookEmailCheckRequestStatusView.as_view(),
        name='email-check-request-status',
    ),
]
