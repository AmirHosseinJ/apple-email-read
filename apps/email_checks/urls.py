from django.urls import path

from apps.email_checks.views import OutlookEmailCheckRequestStatusView, OutlookEmailCheckRunView


urlpatterns = [
    path('email-checks/run/', OutlookEmailCheckRunView.as_view(), name='email-check-run'),
    path(
        'email-checks/requests/<int:request_id>/',
        OutlookEmailCheckRequestStatusView.as_view(),
        name='email-check-request-status',
    ),
]
