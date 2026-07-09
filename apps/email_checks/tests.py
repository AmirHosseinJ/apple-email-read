import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.test import APIClient

from apps.email_checks.models import EmailCheckRequest, Webhook
from apps.email_checks.tasks import run_outlook_check_task
from apps.scraper.exceptions import LoginFailed
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
        self.user = get_user_model().objects.create_user(
            username='person',
            password='test-password',
        )
        self.client.force_authenticate(user=self.user)

    @patch('apps.email_checks.tasks.run_outlook_check')
    @patch('apps.email_checks.notifications.request.urlopen')
    def test_queues_and_reads_outlook_check_through_celery(self, mocked_urlopen, mocked_run_outlook_check):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b''
        mocked_run_outlook_check.return_value = {
            'status': 'otp_found',
            'otp': '123456',
            'found': True,
            'attempts': 1,
            'messages_checked': 1,
        }
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
        )

        queue_response = self.client.post(
            reverse('email-check-run'),
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(queue_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(queue_response.data['queue_status'], 'PENDING')
        self.assertEqual(queue_response.data['email_check_status'], 'queued')
        self.assertTrue(queue_response.data['request_id'])
        self.assertNotIn('task_id', queue_response.data)
        mocked_run_outlook_check.assert_called_once_with(
            email='person@example.com',
            password='secret-password',
            max_messages=1,
            headless=None,
        )

        email_check_request = EmailCheckRequest.objects.get(id=queue_response.data['request_id'])
        self.assertEqual(email_check_request.email, 'person@example.com')
        self.assertEqual(email_check_request.password, 'secret-password')
        self.assertEqual(email_check_request.user, self.user)
        self.assertEqual(email_check_request.webhook, webhook)
        self.assertEqual(email_check_request.status, 'otp_found')
        self.assertEqual(email_check_request.otp, '123456')
        self.assertEqual(email_check_request.total_try, 0)
        self.assertTrue(email_check_request.task_id)
        self.assertIsNotNone(email_check_request.start_at)
        self.assertIsNotNone(email_check_request.finish_at)

        webhook_request = mocked_urlopen.call_args.args[0]
        self.assertEqual(webhook_request.full_url, 'https://webhook.site/callback')
        self.assertEqual(webhook_request.get_method(), 'POST')
        payload = json.loads(webhook_request.data.decode('utf-8'))
        self.assertEqual(payload['request_id'], email_check_request.id)
        self.assertEqual(payload['email'], 'person@example.com')
        self.assertEqual(payload['email_check_status'], 'otp_found')
        self.assertEqual(payload['otp'], '123456')
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['message'], 'Task completed.')
        self.assertEqual(payload['error_message'], '')
        self.assertNotIn('result', payload)
        self.assertNotIn('status', payload)
        self.assertNotIn('total_try', payload)
        self.assertNotIn('finish_at', payload)
        self.assertNotIn('attempts', payload)
        self.assertNotIn('retries', payload)
        self.assertEqual(payload['meta'], {'attempts': 1, 'retries': 0})
        self.assertEqual(list(payload.keys())[-1], 'meta')


class OutlookEmailCheckTaskRetryTests(TestCase):
    @patch('apps.email_checks.tasks.run_outlook_check')
    def test_does_not_retry_incorrect_password(self, mocked_run_outlook_check):
        failure = LoginFailed('That password is incorrect for your Microsoft account.')
        mocked_run_outlook_check.side_effect = failure
        email_check_request = EmailCheckRequest.objects.create(
            email='person@example.com',
            password='secret-password',
            status='queued',
            max_messages=1,
        )

        with patch.object(run_outlook_check_task, 'retry') as mocked_retry:
            with self.assertRaises(LoginFailed) as raised:
                run_outlook_check_task.run(
                    email='person@example.com',
                    password='secret-password',
                    max_messages=1,
                    request_id=email_check_request.id,
                )

        self.assertIs(raised.exception, failure)
        mocked_retry.assert_not_called()
        email_check_request.refresh_from_db()
        self.assertEqual(email_check_request.status, 'failed')
        self.assertEqual(email_check_request.total_try, 0)
        self.assertEqual(
            email_check_request.error_message,
            'That password is incorrect for your Microsoft account.',
        )
        self.assertIsNotNone(email_check_request.finish_at)

    @override_settings(
        CELERY_EMAIL_CHECK_RETRY_COUNT=4,
        CELERY_EMAIL_CHECK_RETRY_DELAY_SECONDS=12,
    )
    @patch('apps.email_checks.tasks.run_outlook_check')
    def test_retries_failed_outlook_check_with_configured_delay(self, mocked_run_outlook_check):
        failure = RuntimeError('browser failed')
        retry_request = RuntimeError('retry requested')
        mocked_run_outlook_check.side_effect = failure
        email_check_request = EmailCheckRequest.objects.create(
            email='person@example.com',
            password='secret-password',
            status='queued',
            max_messages=1,
        )

        with patch.object(run_outlook_check_task, 'retry', side_effect=retry_request) as mocked_retry:
            with self.assertRaises(RuntimeError) as raised:
                run_outlook_check_task.run(
                    email='person@example.com',
                    password='secret-password',
                    max_messages=1,
                    request_id=email_check_request.id,
                )

        self.assertIs(raised.exception, retry_request)
        mocked_retry.assert_called_once_with(
            exc=failure,
            countdown=12,
            max_retries=4,
        )
        email_check_request.refresh_from_db()
        self.assertEqual(email_check_request.status, 'retrying')
        self.assertEqual(email_check_request.total_try, 1)
        self.assertEqual(email_check_request.error_message, 'browser failed')
        self.assertIsNone(email_check_request.finish_at)


class OutlookEmailCheckRunViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='person',
            password='test-password',
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('email-check-run')

    @patch('apps.email_checks.views.run_outlook_check_task.delay')
    def test_queues_outlook_check(self, mocked_delay):
        mocked_delay.return_value = SimpleNamespace(id='task-123')
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
        )
        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['queue_status'], 'PENDING')
        self.assertEqual(response.data['email_check_status'], 'queued')
        self.assertEqual(response.data['message'], 'Request accepted.')
        self.assertNotIn('attempts', response.data)
        self.assertNotIn('retries', response.data)
        self.assertEqual(response.data['meta'], {'attempts': 0, 'retries': 0})
        self.assertTrue(response.data['request_id'])
        self.assertNotIn('task_id', response.data)
        self.assertNotIn('status_url', response.data)
        email_check_request = EmailCheckRequest.objects.get(id=response.data['request_id'])
        mocked_delay.assert_called_once_with(
            email='person@example.com',
            password='secret-password',
            max_messages=1,
            request_id=email_check_request.id,
        )
        self.assertEqual(email_check_request.status, 'queued')
        self.assertEqual(email_check_request.task_id, 'task-123')
        self.assertEqual(email_check_request.user, self.user)
        self.assertEqual(email_check_request.webhook, webhook)

    @patch('apps.email_checks.views.run_outlook_check_task.delay')
    def test_links_outlook_check_to_webhook_for_request_source_ip(self, mocked_delay):
        mocked_delay.return_value = SimpleNamespace(id='task-123')
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
            header_key='X-Callback-Token',
            header_value='secret',
        )

        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        email_check_request = EmailCheckRequest.objects.get(id=response.data['request_id'])
        self.assertEqual(email_check_request.webhook, webhook)

    @patch('apps.email_checks.views.UserNotification')
    @patch('apps.email_checks.views.run_outlook_check_task.delay')
    def test_notifies_webhook_when_queue_fails(self, mocked_delay, mocked_user_notification):
        failure = OperationalError('broker unavailable')
        mocked_delay.side_effect = failure
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
        )

        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        email_check_request = EmailCheckRequest.objects.get()
        self.assertEqual(email_check_request.status, 'queue_failed')
        mocked_user_notification.assert_called_once_with(webhook)
        mocked_user_notification.return_value.send_email_check_result.assert_called_once_with(
            email_check_request,
            status='queue_failed',
            error_message='broker unavailable',
        )

    @patch('apps.email_checks.views.run_outlook_check_task.delay')
    def test_rejects_outlook_check_without_matching_source_ip_webhook(self, mocked_delay):
        mocked_delay.return_value = SimpleNamespace(id='task-123')
        Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
        )

        response = self.client.post(
            self.url,
            {
                'email': 'person@example.com',
                'password': 'secret-password',
                'max_messages': 1,
            },
            format='json',
            REMOTE_ADDR='198.51.100.20',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['queue_status'], 'FAILURE')
        self.assertEqual(response.data['email_check_status'], 'webhook_not_configured')
        self.assertEqual(response.data['detail'], 'No webhook is configured for this request source IP.')
        self.assertIsNone(response.data['otp'])
        self.assertNotIn('attempts', response.data)
        self.assertNotIn('retries', response.data)
        self.assertEqual(response.data['meta'], {'attempts': 0, 'retries': 0})
        self.assertFalse(EmailCheckRequest.objects.exists())
        mocked_delay.assert_not_called()

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


class UserNotificationTests(TestCase):
    @patch('apps.email_checks.notifications.request.urlopen')
    def test_sends_email_check_result_to_configured_webhook(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b''
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
            header_key='X-Callback-Token',
            header_value='secret',
        )
        email_check_request = EmailCheckRequest.objects.create(
            email='person@example.com',
            password='secret-password',
            status='otp_found',
            otp='123456',
            total_try=0,
            max_messages=1,
            finish_at=timezone.now(),
            webhook=webhook,
        )

        from apps.email_checks.notifications import UserNotification

        UserNotification(webhook).send_email_check_result(
            email_check_request,
            status='otp_found',
            result={
                'status': 'otp_found',
                'otp': '123456',
                'found': True,
                'current_url': 'https://outlook.live.com/mail/',
                'title': 'Mail - Gold Appleid - Outlook',
                'attempts': 1,
            },
        )

        webhook_request = mocked_urlopen.call_args.args[0]
        self.assertEqual(webhook_request.full_url, 'https://webhook.site/callback')
        self.assertEqual(webhook_request.get_method(), 'POST')
        self.assertEqual(webhook_request.headers['X-callback-token'], 'secret')
        payload = json.loads(webhook_request.data.decode('utf-8'))
        self.assertEqual(payload['request_id'], email_check_request.id)
        self.assertEqual(payload['email'], 'person@example.com')
        self.assertEqual(payload['email_check_status'], 'otp_found')
        self.assertEqual(payload['otp'], '123456')
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['message'], 'Task completed.')
        self.assertNotIn('result', payload)
        self.assertNotIn('status', payload)
        self.assertNotIn('total_try', payload)
        self.assertNotIn('finish_at', payload)
        self.assertNotIn('attempts', payload)
        self.assertNotIn('retries', payload)
        self.assertEqual(payload['meta'], {'attempts': 1, 'retries': 0})
        self.assertNotIn('current_url', payload['meta'])
        self.assertNotIn('title', payload['meta'])
        self.assertEqual(list(payload.keys())[-1], 'meta')

    @patch('apps.email_checks.notifications.time.sleep')
    @patch('apps.email_checks.notifications.logger.info')
    @patch('apps.email_checks.notifications.logger.warning')
    @patch('apps.email_checks.notifications.request.urlopen')
    def test_does_not_raise_when_webhook_request_fails(
        self,
        mocked_urlopen,
        mocked_logger_warning,
        mocked_logger_info,
        mocked_sleep,
    ):
        mocked_urlopen.side_effect = OSError('network unavailable')
        webhook = Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/callback',
        )
        email_check_request = EmailCheckRequest.objects.create(
            email='person@example.com',
            password='secret-password',
            status='failed',
            total_try=0,
            max_messages=1,
            finish_at=timezone.now(),
            webhook=webhook,
        )

        from apps.email_checks.notifications import UserNotification

        UserNotification(webhook).send_email_check_result(
            email_check_request,
            status='failed',
            error_message='That password is incorrect for your Microsoft account.',
        )

        self.assertEqual(mocked_urlopen.call_count, 3)
        self.assertEqual(mocked_logger_info.call_count, 3)
        self.assertEqual(mocked_logger_warning.call_count, 3)
        self.assertEqual(mocked_sleep.call_count, 2)
        mocked_logger_info.assert_any_call(
            'Sending email check result webhook: request_id=%s webhook_id=%s url=%s attempt=%s of %s timeout=%s',
            email_check_request.id,
            webhook.id,
            'https://webhook.site/callback',
            1,
            3,
            3,
        )
        mocked_logger_warning.assert_any_call(
            'Failed to send email check result webhook: request_id=%s webhook_id=%s url=%s attempt=%s of %s error=%s',
            email_check_request.id,
            webhook.id,
            'https://webhook.site/callback',
            3,
            3,
            mocked_urlopen.side_effect,
        )


class AutomationWebhookViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='person',
            password='test-password',
        )
        self.url = reverse('automation-webhook')

    def test_requires_authentication(self):
        response = self.client.get(
            self.url,
            {
                'webhook': 'https://webhook.site/1f0186e0-b8de-495c-a5be-4569dddae1fd',
            },
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_creates_webhook_for_request_source_ip(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.url,
            {
                'webhook': 'https://webhook.site/1f0186e0-b8de-495c-a5be-4569dddae1fd',
                'header_key': 'X-Callback-Token',
                'header_value': 'your-secret-token',
            },
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'created')
        self.assertEqual(response.data['ip'], '203.0.113.10')
        self.assertEqual(response.data['webhook'], 'https://webhook.site/1f0186e0-b8de-495c-a5be-4569dddae1fd')
        self.assertEqual(response.data['header_key'], 'X-Callback-Token')
        self.assertNotIn('header_value', response.data)

        webhook = Webhook.objects.get(ip='203.0.113.10')
        self.assertEqual(webhook.webhook, 'https://webhook.site/1f0186e0-b8de-495c-a5be-4569dddae1fd')
        self.assertEqual(webhook.header_key, 'X-Callback-Token')
        self.assertEqual(webhook.header_value, 'your-secret-token')

    def test_updates_existing_webhook_for_request_source_ip(self):
        self.client.force_authenticate(user=self.user)
        Webhook.objects.create(
            ip='203.0.113.10',
            webhook='https://webhook.site/old',
            header_key='Old-Header',
            header_value='old-secret',
        )

        response = self.client.get(
            self.url,
            {
                'webhook': 'https://webhook.site/new',
                'header_key': 'X-Callback-Token',
                'header_value': 'new-secret',
            },
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'updated')
        self.assertEqual(Webhook.objects.count(), 1)

        webhook = Webhook.objects.get(ip='203.0.113.10')
        self.assertEqual(webhook.webhook, 'https://webhook.site/new')
        self.assertEqual(webhook.header_key, 'X-Callback-Token')
        self.assertEqual(webhook.header_value, 'new-secret')

    def test_rejects_invalid_webhook_url(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.url,
            {
                'webhook': 'not-a-url',
            },
            REMOTE_ADDR='203.0.113.10',
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
        self.assertIsNone(runner.options.headless)

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

    @patch('apps.email_checks.management.commands.outlook_check_mail_celery.OutlookCheckMailRunner.run', autospec=True)
    def test_allows_enabling_headless_browser(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(id='task-123')

        call_command(
            'outlook_check_mail_celery',
            email='person@example.com',
            password='secret-password',
            headless=True,
            stdout=StringIO(),
        )

        runner = mocked_run.call_args.args[0]
        self.assertTrue(runner.options.headless)

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


class OutlookLoginPreviewCommandTests(TestCase):
    @patch('apps.email_checks.management.commands.outlook_login_preview.OutlookLoginPreviewRunner.run', autospec=True)
    def test_uses_env_headless_by_default(self, mocked_run):
        mocked_run.return_value = {
            'status': 'email_submitted',
            'title': 'Outlook',
            'current_url': 'https://outlook.live.com/mail/',
        }

        call_command(
            'outlook_login_preview',
            email='person@example.com',
            stdout=StringIO(),
        )

        runner = mocked_run.call_args.args[0]
        self.assertIsNone(runner.options.headless)

    @patch('apps.email_checks.management.commands.outlook_login_preview.OutlookLoginPreviewRunner.run', autospec=True)
    def test_allows_overriding_headless_browser(self, mocked_run):
        mocked_run.return_value = {
            'status': 'email_submitted',
            'title': 'Outlook',
            'current_url': 'https://outlook.live.com/mail/',
        }

        call_command(
            'outlook_login_preview',
            email='person@example.com',
            headless=False,
            stdout=StringIO(),
        )

        runner = mocked_run.call_args.args[0]
        self.assertFalse(runner.options.headless)


class OutlookEmailCheckTaskStatusViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='person',
            password='test-password',
        )
        self.client.force_authenticate(user=self.user)
        self.email_check_request = EmailCheckRequest.objects.create(
            email='person@example.com',
            password='secret-password',
            status='queued',
            max_messages=1,
            task_id='task-123',
            user=self.user,
        )
        self.url = reverse(
            'email-check-request-status',
            kwargs={'request_id': self.email_check_request.id},
        )

    @patch('apps.email_checks.views.AsyncResult')
    @override_settings(CELERY_EMAIL_CHECK_RETRY_COUNT=4)
    def test_returns_successful_task_result(self, mocked_async_result):
        self.email_check_request.total_try = 1
        self.email_check_request.save(update_fields=['total_try'])
        mocked_async_result.return_value = SimpleNamespace(
            state='SUCCESS',
            result={'status': 'otp_found', 'otp': '123456'},
            successful=lambda: True,
            failed=lambda: False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['request_id'], self.email_check_request.id)
        self.assertNotIn('total_retries', response.data)
        self.assertNotIn('remaining_tries', response.data)
        self.assertNotIn('attempts', response.data)
        self.assertNotIn('retries', response.data)
        self.assertEqual(response.data['meta'], {'attempts': 2, 'retries': 1})
        self.assertNotIn('task_id', response.data)
        self.assertEqual(response.data['queue_status'], 'SUCCESS')
        self.assertEqual(response.data['email_check_status'], 'otp_found')
        self.assertNotIn('state', response.data)
        self.assertNotIn('status', response.data)
        self.assertEqual(response.data['otp'], '123456')
        self.assertNotIn('result', response.data)
        mocked_async_result.assert_called_once_with('task-123')

    @patch('apps.email_checks.views.AsyncResult')
    @override_settings(CELERY_EMAIL_CHECK_RETRY_COUNT=4)
    def test_returns_pending_task_state(self, mocked_async_result):
        self.email_check_request.total_try = 2
        self.email_check_request.save(update_fields=['total_try'])
        mocked_async_result.return_value = SimpleNamespace(
            state='PENDING',
            successful=lambda: False,
            failed=lambda: False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['queue_status'], 'PENDING')
        self.assertEqual(response.data['email_check_status'], 'pending')
        self.assertNotIn('state', response.data)
        self.assertNotIn('status', response.data)
        self.assertNotIn('attempts', response.data)
        self.assertNotIn('retries', response.data)
        self.assertEqual(response.data['meta'], {'attempts': 3, 'retries': 2})

    @override_settings(CELERY_EMAIL_CHECK_RETRY_COUNT=4)
    def test_returns_retry_counts_without_task_id(self):
        self.email_check_request.task_id = ''
        self.email_check_request.status = 'queue_failed'
        self.email_check_request.total_try = 5
        self.email_check_request.error_message = 'broker unavailable'
        self.email_check_request.save(
            update_fields=['task_id', 'status', 'total_try', 'error_message'],
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['queue_status'], 'QUEUE_FAILED')
        self.assertEqual(response.data['email_check_status'], 'queue_failed')
        self.assertNotIn('state', response.data)
        self.assertNotIn('status', response.data)
        self.assertIsNone(response.data['otp'])
        self.assertNotIn('attempts', response.data)
        self.assertNotIn('retries', response.data)
        self.assertEqual(response.data['meta'], {'attempts': 6, 'retries': 5})
        self.assertEqual(response.data['detail'], 'broker unavailable')
