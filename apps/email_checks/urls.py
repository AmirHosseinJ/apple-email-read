from django.urls import path

from apps.email_checks.views import OutlookEmailCheckRunView


urlpatterns = [
    path('email-checks/run/', OutlookEmailCheckRunView.as_view(), name='email-check-run'),
]
