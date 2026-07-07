from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from config.celery import app as celery_app


class CeleryEagerTestMixin:
    celery_test_config = {
        'task_always_eager': True,
        'task_store_eager_result': True,
        'task_eager_propagates': True,
        'result_backend': 'cache+memory://',
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._previous_celery_config = {
            key: celery_app.conf.get(key) for key in cls.celery_test_config
        }
        cls._previous_celery_backend = celery_app._backend
        celery_app.set_current()
        celery_app.conf.update(**cls.celery_test_config)
        cls._clear_celery_backend_cache()

    @classmethod
    def tearDownClass(cls):
        celery_app.conf.update(**cls._previous_celery_config)
        cls._clear_celery_backend_cache()
        if cls._previous_celery_backend is not None:
            celery_app._backend = cls._previous_celery_backend
        super().tearDownClass()

    @staticmethod
    def _clear_celery_backend_cache():
        celery_app._backend_cache = None
        if hasattr(celery_app._local, 'backend'):
            del celery_app._local.backend


class OutlookEmailCheckCeleryFlowTests(CeleryEagerTestMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('apps.email_checks.tasks.run_outlook_check')
    def test_queues_and_reads_outlook_check_through_celery(self, mocked_run_outlook_check):
        mocked_run_outlook_check.return_value = {
            'status': 'otp_found',
            'otp': '123456',
            'messages_checked': 1,
        }

        queue_response = self.client.post(
            reverse('email-check-run'),
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
        )

        self.assertEqual(queue_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(queue_response.data['status'], 'queued')
        self.assertTrue(queue_response.data['task_id'])
        mocked_run_outlook_check.assert_called_once_with(
            email='person@example.com',
            password='secret-password',
            max_messages=1,
            headless=True,
        )

        status_response = self.client.get(
            reverse(
                'email-check-task-status',
                kwargs={'task_id': queue_response.data['task_id']},
            )
        )

        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data['state'], 'SUCCESS')
        self.assertEqual(status_response.data['status'], 'success')
        self.assertEqual(status_response.data['result']['otp'], '123456')
        self.assertEqual(status_response.data['result']['messages_checked'], 1)


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


class OutlookCheckMailCommandTests(TestCase):
    @patch('apps.email_checks.management.commands.outlook_check_mail_celery.OutlookCheckMailRunner.run')
    def test_queues_outlook_check_task(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(id='task-123')

        call_command(
            'outlook_check_mail_celery',
            email='person@example.com',
            password='secret-password',
            max_messages=1,
            stdout=StringIO(),
        )

        mocked_run.assert_called_once_with()

    @patch('apps.email_checks.management.commands.outlook_check_mail_celery.OutlookCheckMailRunner.run', autospec=True)
    def test_defaults_max_messages_to_10(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(id='task-123')

        call_command(
            'outlook_check_mail_celery',
            email='person@example.com',
            password='secret-password',
            stdout=StringIO(),
        )

        runner = mocked_run.call_args.args[0]
        self.assertEqual(runner.options.max_messages, 10)
        self.assertTrue(runner.options.headless)

    @patch('apps.email_checks.management.commands.outlook_check_mail_celery.OutlookCheckMailRunner.run', autospec=True)
    def test_allows_disabling_headless_browser(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(id='task-123')

        call_command(
            'outlook_check_mail_celery',
            email='person@example.com',
            password='secret-password',
            headless=False,
            stdout=StringIO(),
        )

        runner = mocked_run.call_args.args[0]
        self.assertFalse(runner.options.headless)

    def test_rejects_invalid_max_messages(self):
        with self.assertRaisesMessage(CommandError, '--max-messages must be at least 1.'):
            call_command(
                'outlook_check_mail_celery',
                email='person@example.com',
                password='secret-password',
                max_messages=0,
            )

    def test_rejects_too_many_messages(self):
        with self.assertRaisesMessage(CommandError, '--max-messages must be at most 50.'):
            call_command(
                'outlook_check_mail_celery',
                email='person@example.com',
                password='secret-password',
                max_messages=51,
            )


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
