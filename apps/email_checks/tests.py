from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class OutlookEmailCheckRunViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('email-check-run')

    @patch('apps.email_checks.views.run_outlook_check')
    def test_runs_outlook_check(self, mocked_run_outlook_check):
        mocked_run_outlook_check.return_value = {
            'status': 'otp_found',
            'otp': '123456',
            'attempts': 1,
            'found': True,
        }

        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['result']['status'], 'otp_found')
        self.assertEqual(response.data['result']['otp'], '123456')
        mocked_run_outlook_check.assert_called_once_with(
            email='person@example.com',
            password='secret-password',
            max_messages=1,
        )

    def test_rejects_invalid_email(self):
        response = self.client.post(
            self.url,
            {
                'email': 'not-an-email',
                'password': 'secret-password',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
