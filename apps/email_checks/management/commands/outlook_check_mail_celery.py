from argparse import BooleanOptionalAction
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.email_checks.models import EmailCheckRequest
from apps.email_checks.tasks import run_outlook_check_task


@dataclass(frozen=True)
class OutlookCheckMailOptions:
    email: str
    password: str
    max_messages: int
    headless: bool | None

    @classmethod
    def from_command_options(cls, options):
        return cls(
            email=options['email'],
            password=options['password'],
            max_messages=options['max_messages'],
            headless=options['headless'],
        )


class OutlookCheckMailRunner:
    def __init__(self, options: OutlookCheckMailOptions):
        self.options = options

    @classmethod
    def from_command_options(cls, options):
        return cls(OutlookCheckMailOptions.from_command_options(options))

    def run(self):
        email_check_request = EmailCheckRequest.objects.create(
            email=self.options.email,
            password=self.options.password,
            status='queued',
            max_messages=self.options.max_messages,
        )
        try:
            task = run_outlook_check_task.delay(
                email=self.options.email,
                password=self.options.password,
                max_messages=self.options.max_messages,
                headless=self.options.headless,
                request_id=email_check_request.id,
            )
        except OperationalError as exc:
            email_check_request.status = 'queue_failed'
            email_check_request.error_message = str(exc)
            email_check_request.finish_at = timezone.now()
            email_check_request.save(update_fields=['status', 'error_message', 'finish_at', 'updated_at'])
            raise

        email_check_request.task_id = task.id
        email_check_request.save(update_fields=['task_id', 'updated_at'])
        return task


class Command(BaseCommand):
    help = 'Queue an Outlook email check Celery task.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument(
            '--max-messages',
            type=int,
            default=10,
            help='Maximum number of Outlook messages to inspect. Defaults to 10.',
        )
        parser.add_argument(
            '--headless',
            action=BooleanOptionalAction,
            default=None,
            help='Override EMAIL_CHECKS_HEADLESS for this command run.',
        )

    def handle(self, *args, **options):
        if options['max_messages'] < 1:
            raise CommandError('--max-messages must be at least 1.')
        if options['max_messages'] > 50:
            raise CommandError('--max-messages must be at most 50.')

        runner = OutlookCheckMailRunner.from_command_options(options)

        try:
            task = runner.run()
        except OperationalError as exc:
            raise CommandError(f'Failed to queue email check task: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('queued'))
        self.stdout.write(f'Task ID: {task.id}')
