import logging
import re
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.scraper import selectors
from apps.scraper.browser import chromium_page
from apps.scraper.config import otp_attempt_timeout_seconds, otp_retry_count, otp_retry_wait_seconds
from apps.scraper.exceptions import LoginFailed, OutlookHighDemand, ScraperTimeout
from apps.scraper.helpers import click_and_switch_tab_if_opened, wait_and_click_first

logger = logging.getLogger(__name__)

OUTLOOK_LOGIN_URL = "https://outlook.live.com/mail/"
DEFAULT_TIMEOUT_MS = 60_000
OTP_PATTERN = re.compile(r'(?<!\d)(\d{6})(?!\d)')
APPLE_MARKERS = ('apple', 'icloud')
HIGH_DEMAND_ERROR_MESSAGE = 'We are currently experiencing high demand. Please wait and try again later.'
INCORRECT_PASSWORD_ERROR_MESSAGE = 'That password is incorrect for your Microsoft account.'


class OutlookClient:
    def __init__(self, page, *, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.page = page
        self.timeout_ms = timeout_ms
        self.page.set_default_timeout(timeout_ms)

    def open_login_page(self) -> None:
        logger.info("Navigating to Outlook mail page")
        self.page.goto(OUTLOOK_LOGIN_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(2000)
        self.raise_if_high_demand_page()

    def raise_if_high_demand_page(self) -> None:
        high_demand_message = self.page.locator(selectors.HIGH_DEMAND_MESSAGE)

        try:
            high_demand_message.wait_for(state="visible", timeout=3_000)
        except PlaywrightTimeoutError:
            return

        raise OutlookHighDemand(HIGH_DEMAND_ERROR_MESSAGE)

    def start_login_sequence(self) -> None:
        self.open_login_page()
        self.continue_to_authentication()

    def continue_to_authentication(self):
        logger.info("Continuing from Outlook landing page to Microsoft authentication")
        self.page = click_and_switch_tab_if_opened(
            self.page,
            selectors.SIGN_IN_BUTTON,
            "authentication entry",
            15000
        )
        return self.page

    def fill_email(self, email: str) -> None:
        email_input = self.page.locator(selectors.EMAIL_INPUT)
        email_input.wait_for(state="visible", timeout=15_000)
        email_input.fill(email)

    def submit_next(self) -> None:
        wait_and_click_first(self.page, selectors.SUBMIT_NEXT_BUTTON, 'Next button (email)')

    def submit_password(self) -> None:
        wait_and_click_first(self.page, selectors.SUBMIT_PASSWORD_BUTTON, 'Next button (password)')

    def raise_if_incorrect_password(self) -> None:
        incorrect_password_error = self.page.locator(selectors.INCORRECT_PASSWORD_ERROR)

        try:
            incorrect_password_error.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError:
            return

        raise LoginFailed(INCORRECT_PASSWORD_ERROR_MESSAGE)

    def is_get_code_sign_in_page(self) -> bool:
        title = self.page.locator(selectors.GET_CODE_SIGN_IN_TITLE)

        try:
            title.wait_for(state="visible", timeout=8_000)
        except PlaywrightTimeoutError:
            return False

        return True

    def click_use_password(self) -> None:
        use_password_button = self.page.locator(selectors.USE_PASSWORD_BUTTON).first
        use_password_button.wait_for(state="visible", timeout=15_000)
        use_password_button.click()

    def use_password_if_code_prompt_is_shown(self) -> bool:
        if not self.is_get_code_sign_in_page():
            return False

        self.click_use_password()
        return True

    def fill_password(self, password: str) -> None:
        password_input = self.page.locator(selectors.PASSWORD_INPUT)
        password_input.wait_for(state="visible", timeout=15_000)
        password_input.fill(password)

    def is_stay_signed_in_page(self) -> bool:
        title = self.page.locator(selectors.STAY_SIGNED_IN_TITLE)

        try:
            title.wait_for(state="visible", timeout=8_000)
        except PlaywrightTimeoutError:
            return False

        return True

    def click_stay_signed_in_no(self) -> None:
        no_button = self.page.locator(selectors.STAY_SIGNED_IN_NO_BUTTON).first
        no_button.wait_for(state="visible", timeout=15_000)
        no_button.click()

    def decline_stay_signed_in_if_shown(self) -> bool:
        if not self.is_stay_signed_in_page():
            return False

        self.click_stay_signed_in_no()
        return True

    def is_protect_account_page(self, *, timeout: int = 8_000) -> bool:
        title = self.page.locator(selectors.PROTECT_ACCOUNT_TITLE)

        try:
            title.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            return False

        return True

    def click_protect_account_skip(self) -> None:
        # skip_button = self.page.locator(selectors.PROTECT_ACCOUNT_SKIP_BUTTON).first
        # skip_button.wait_for(state="visible", timeout=15_000)
        # skip_button.click()
        wait_and_click_first(self.page, selectors.PROTECT_ACCOUNT_SKIP_BUTTON, 'Skip for now', timeout=15_000)

    def skip_protect_account_if_shown(self) -> bool:
        if not self.is_protect_account_page():
            return False

        for attempt in range(2):
            self.click_protect_account_skip()
            self.page.wait_for_timeout(1_000)

            if not self.is_protect_account_page(timeout=3_000):
                return True

            logger.info("Protect account page still visible after skip attempt %s", attempt + 1)

        return True

    def is_outlook_layout_dialog_visible(self, *, timeout: int = 3_000) -> bool:
        title = self.page.locator(selectors.OUTLOOK_LAYOUT_DIALOG_TITLE)

        try:
            title.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            return False

        return True

    def click_outlook_layout_mailbox_recommended(self) -> None:
        wait_and_click_first(
            self.page,
            selectors.OUTLOOK_LAYOUT_MAILBOX_RECOMMENDED_BUTTON,
            'Mailbox (Recommended)',
            timeout=15_000,
        )

    def choose_outlook_mailbox_layout_if_shown(self) -> bool:
        if not self.is_outlook_layout_dialog_visible():
            return False

        logger.info("Choosing Outlook Mailbox (Recommended) layout")
        self.click_outlook_layout_mailbox_recommended()
        self.page.wait_for_timeout(1_000)
        return True

    def wait_for_successful_login(self) -> None:
        self.page.wait_for_function(
            """
            () => (
                window.location.hostname === 'outlook.live.com'
                && window.location.pathname.startsWith('/mail')
                && document.title.includes('Outlook')
            )
            """,
            timeout=30_000,
        )

    def search_for_apple_messages(self, *, timeout_ms: int = 3_000) -> bool:
        search_input = self.page.locator(selectors.OUTLOOK_SEARCH_INPUT).first

        try:
            search_input.wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return False

        search_input.fill('Apple')
        search_input.press('Enter')
        return True

    def visible_text(self, *, timeout_ms: int = 5_000) -> str:
        return self.page.locator('body').inner_text(timeout=timeout_ms)

    def find_latest_apple_otp_once(self, *, attempt_timeout_seconds: int = 10) -> str | None:
        deadline = monotonic() + max(0, attempt_timeout_seconds)

        def remaining_ms(*, maximum: int) -> int:
            return max(0, min(maximum, int((deadline - monotonic()) * 1000)))

        timeout_ms = remaining_ms(maximum=3_000)
        if timeout_ms == 0:
            return None
        search_started = self.search_for_apple_messages(timeout_ms=timeout_ms)

        timeout_ms = remaining_ms(maximum=5_000)
        if timeout_ms == 0:
            return None
        otp = extract_latest_apple_otp(self.visible_text(timeout_ms=timeout_ms))
        if otp or not search_started:
            return otp

        timeout_ms = remaining_ms(maximum=3_000)
        if timeout_ms == 0 or not self.open_latest_visible_message(timeout_ms=timeout_ms):
            return None

        timeout_ms = remaining_ms(maximum=5_000)
        if timeout_ms == 0:
            return None
        return extract_latest_apple_otp(self.visible_text(timeout_ms=timeout_ms))

    def open_latest_visible_message(self, *, timeout_ms: int = 3_000) -> bool:
        message = self.page.locator(selectors.OUTLOOK_MESSAGE_ROW).first

        try:
            message.wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return False

        message.click()
        self.page.wait_for_timeout(500)
        return True

    def find_latest_apple_otp(
        self,
        *,
        retry_count: int | None = None,
        retry_wait_seconds: int | None = None,
        attempt_timeout_seconds: int | None = None,
    ) -> dict:
        retries = otp_retry_count() if retry_count is None else retry_count
        wait_seconds = otp_retry_wait_seconds() if retry_wait_seconds is None else retry_wait_seconds
        attempt_seconds = (
            otp_attempt_timeout_seconds() if attempt_timeout_seconds is None else attempt_timeout_seconds
        )

        self.choose_outlook_mailbox_layout_if_shown()

        for attempt in range(retries + 1):
            if attempt > 0:
                self.page.wait_for_timeout(wait_seconds * 1000)

            logger.info("[RETRY] Searching Outlook inbox for Apple OTP on attempt %s of %s", attempt + 1, retries + 1)
            otp = self.find_latest_apple_otp_once(attempt_timeout_seconds=attempt_seconds)
            if otp:
                logger.info("Found Apple OTP: %s on attempt %s", otp, attempt + 1)
                return {
                    'otp': otp,
                    'attempts': attempt + 1,
                    'found': True,
                }

        return {
            'otp': None,
            'attempts': retries + 1,
            'found': False,
        }


def run_email_entry_sequence(
    *,
    email: str,
    password: str | None = None,
    headless: bool | None = None,
    hold_open_seconds: int = 0,
) -> dict:
    try:
        with chromium_page(headless=headless) as page:
            client = OutlookClient(page)
            client.start_login_sequence()
            client.fill_email(email)
            client.submit_next()

            status = 'email_submitted'
            if client.use_password_if_code_prompt_is_shown():
                status = 'password_method_selected'

            if password:
                client.fill_password(password)
                client.submit_password()
                status = 'password_filled'
                client.raise_if_incorrect_password()

                if client.skip_protect_account_if_shown():
                    status = 'protect_account_skipped'

                if client.decline_stay_signed_in_if_shown():
                    status = 'stay_signed_in_declined'

                client.wait_for_successful_login()
                status = 'login_successful'
                if client.choose_outlook_mailbox_layout_if_shown():
                    status = 'outlook_mailbox_layout_selected'

                otp_result = client.find_latest_apple_otp()
                status = 'otp_found' if otp_result['found'] else 'otp_not_found'

            if hold_open_seconds > 0:
                client.page.wait_for_timeout(hold_open_seconds * 1000)

            result = {
                'status': status,
                'current_url': safe_url(client.page.url),
                'title': client.page.title(),
            }
            if password:
                result.update(otp_result)

            return result
    except PlaywrightTimeoutError as exc:
        raise ScraperTimeout('Outlook email entry sequence did not finish before the timeout.') from exc


def check_outlook_email(
    *,
    email: str,
    password: str,
    max_messages: int = 10,
    headless: bool | None = None,
) -> dict:
    return run_email_entry_sequence(
        email=email,
        password=password,
        headless=headless,
    )


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))


def extract_latest_apple_otp(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    seen = set()
    matches = []

    for index, line in enumerate(lines):
        window = ' '.join(lines[max(0, index - 2):index + 3])
        lowered_window = window.lower()
        if not any(marker in lowered_window for marker in APPLE_MARKERS):
            continue

        for code in OTP_PATTERN.findall(window):
            if code not in seen:
                seen.add(code)
                matches.append(code)

    if matches:
        return matches[0]

    lowered_text = text.lower()
    if any(marker in lowered_text for marker in APPLE_MARKERS):
        match = OTP_PATTERN.search(text)
        if match:
            return match.group(1)

    return None
