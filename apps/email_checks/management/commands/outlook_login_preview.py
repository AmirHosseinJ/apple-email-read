from argparse import BooleanOptionalAction
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from apps.scraper.exceptions import OutlookScraperError
from apps.scraper.outlook_client import run_email_entry_sequence


@dataclass(frozen=True)
class OutlookLoginPreviewOptions:
    email: str
    password: str | None
    headless: bool | None
    hold_open_seconds: int

    @classmethod
    def from_command_options(cls, options):
        return cls(
            email=options['email'],
            password=options.get('password'),
            headless=options['headless'],
            hold_open_seconds=options['hold_open_seconds'],
        )


class OutlookLoginPreviewRunner:
    def __init__(self, options: OutlookLoginPreviewOptions):
        self.options = options

    @classmethod
    def from_command_options(cls, options):
        return cls(OutlookLoginPreviewOptions.from_command_options(options))

    def run(self) -> dict:
        return run_email_entry_sequence(
            email=self.options.email,
            password=self.options.password,
            headless=self.options.headless,
            hold_open_seconds=self.options.hold_open_seconds,
        )


class Command(BaseCommand):
    help = 'Open Outlook in Playwright, continue to authentication, and fill the email field.'

    def add_arguments(self, parser):
        self._add_login_arguments(parser)

    def handle(self, *args, **options):
        runner = OutlookLoginPreviewRunner.from_command_options(options)

        try:
            result = runner.run()
        except OutlookScraperError as exc:
            raise CommandError(str(exc)) from exc

        self._write_result(result)

    def _add_login_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--password')
        parser.add_argument(
            '--headless',
            action=BooleanOptionalAction,
            default=None,
            help='Override EMAIL_CHECKS_HEADLESS for this command run.',
        )
        parser.add_argument(
            '--hold-open-seconds',
            type=int,
            default=30,
            help='Keep the browser open after filling credentials. Defaults to 30 seconds.',
        )

    def _write_result(self, result):
        self.stdout.write(self.style.SUCCESS(result['status']))
        self.stdout.write(f"Title: {result['title']}")
        self.stdout.write(f"URL: {result['current_url']}")
