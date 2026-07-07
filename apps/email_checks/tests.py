from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class OutlookEmailCheckRunViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('email-check-run')

    @patch('apps.email_checks.views.run_outlook_check_task.delay')
    def test_queues_outlook_check(self, mocked_delay):
        mocked_delay.return_value = SimpleNamespace(id='task-123')
        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'queued')
        self.assertEqual(response.data['task_id'], 'task-123')
        self.assertIn('/api/email-checks/tasks/task-123/', response.data['status_url'])
        mocked_delay.assert_called_once_with(
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


class OutlookEmailCheckTaskStatusViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('email-check-task-status', kwargs={'task_id': 'task-123'})

    @patch('apps.email_checks.views.AsyncResult')
    def test_returns_successful_task_result(self, mocked_async_result):
        mocked_async_result.return_value = SimpleNamespace(
            state='SUCCESS',
            result={'status': 'otp_found', 'otp': '123456'},
            successful=lambda: True,
            failed=lambda: False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['task_id'], 'task-123')
        self.assertEqual(response.data['state'], 'SUCCESS')
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['result']['otp'], '123456')
        mocked_async_result.assert_called_once_with('task-123')

    @patch('apps.email_checks.views.AsyncResult')
    def test_returns_pending_task_state(self, mocked_async_result):
        mocked_async_result.return_value = SimpleNamespace(
            state='PENDING',
            successful=lambda: False,
            failed=lambda: False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'pending')
