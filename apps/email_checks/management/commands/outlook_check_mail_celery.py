from argparse import BooleanOptionalAction
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from kombu.exceptions import OperationalError

from apps.email_checks.tasks import run_outlook_check_task


@dataclass(frozen=True)
class OutlookCheckMailOptions:
    email: str
    password: str
    max_messages: int
    headless: bool

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
        return run_outlook_check_task.delay(
            email=self.options.email,
            password=self.options.password,
            max_messages=self.options.max_messages,
            headless=self.options.headless,
        )


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
            default=True,
            help='Run the Outlook browser in headless mode. Defaults to true.',
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
