from django.test import SimpleTestCase
from django.test import override_settings
from unittest.mock import patch

from apps.scraper import selectors
from apps.scraper.browser import _browser_launch_options
from apps.scraper.config import (
    browser_headless,
    browser_proxy,
    otp_attempt_timeout_seconds,
    otp_retry_count,
    otp_retry_wait_seconds,
)
from apps.scraper.exceptions import LoginFailed, OutlookHighDemand
from apps.scraper.outlook_client import (
    HIGH_DEMAND_ERROR_MESSAGE,
    INCORRECT_PASSWORD_ERROR_MESSAGE,
    OUTLOOK_LOGIN_URL,
    OutlookClient,
    extract_latest_apple_otp,
    safe_url,
)


class FakeLocator:
    def __init__(self, *, visible=True, text='', visible_sequence=None):
        self.filled_value = None
        self.waited_for = None
        self.wait_calls = []
        self.visible = visible
        self.visible_sequence = list(visible_sequence) if visible_sequence is not None else None
        self.clicked = False
        self.click_count = 0
        self.first = self
        self.pressed_key = None
        self.text = text

    def wait_for(self, *, state, timeout):
        visible = self.visible
        if self.visible_sequence is not None:
            visible = self.visible_sequence.pop(0) if self.visible_sequence else self.visible

        self.waited_for = {'state': state, 'timeout': timeout}
        self.wait_calls.append(self.waited_for)

        if state == 'visible' and not visible:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

            raise PlaywrightTimeoutError('not visible')

    def fill(self, value):
        self.filled_value = value

    def click(self, **kwargs):
        self.clicked = True
        self.click_count += 1

    def highlight(self):
        pass

    def scroll_into_view_if_needed(self):
        pass

    def bounding_box(self):
        return None

    def press(self, key):
        self.pressed_key = key

    def inner_text(self, *, timeout):
        return self.text


class FakePage:
    def __init__(self):
        self.default_timeout = None
        self.goto_call = None
        self.locators = {}
        self.wait_for_function_call = None
        self.waited_timeout = None

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def goto(self, url, *, wait_until):
        self.goto_call = {'url': url, 'wait_until': wait_until}

    def locator(self, selector):
        self.last_selector = selector
        if selector not in self.locators:
            self.locators[selector] = FakeLocator()
        return self.locators[selector]

    def wait_for_function(self, expression, *, timeout):
        self.wait_for_function_call = {'expression': expression, 'timeout': timeout}

    def wait_for_timeout(self, timeout):
        self.waited_timeout = timeout


class OutlookClientTests(SimpleTestCase):
    def test_open_login_page(self):
        page = FakePage()
        page.locators[selectors.HIGH_DEMAND_MESSAGE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        client.open_login_page()

        self.assertEqual(page.goto_call, {'url': OUTLOOK_LOGIN_URL, 'wait_until': 'domcontentloaded'})

    def test_open_login_page_raises_for_high_demand_page(self):
        page = FakePage()
        page.locators[selectors.HIGH_DEMAND_MESSAGE] = FakeLocator()
        client = OutlookClient(page)

        with self.assertRaisesMessage(OutlookHighDemand, HIGH_DEMAND_ERROR_MESSAGE):
            client.open_login_page()

        self.assertEqual(page.goto_call, {'url': OUTLOOK_LOGIN_URL, 'wait_until': 'domcontentloaded'})
        self.assertEqual(
            page.locators[selectors.HIGH_DEMAND_MESSAGE].waited_for,
            {'state': 'visible', 'timeout': 3_000},
        )

    def test_fill_email(self):
        page = FakePage()
        client = OutlookClient(page)

        client.fill_email('person@example.com')

        email_locator = page.locators[selectors.EMAIL_INPUT]

        self.assertEqual(page.last_selector, selectors.EMAIL_INPUT)
        self.assertEqual(email_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertEqual(email_locator.filled_value, 'person@example.com')

    def test_fill_password(self):
        page = FakePage()
        client = OutlookClient(page)

        client.fill_password('secret-password')

        password_locator = page.locators[selectors.PASSWORD_INPUT]

        self.assertEqual(page.last_selector, selectors.PASSWORD_INPUT)
        self.assertEqual(password_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertEqual(password_locator.filled_value, 'secret-password')

    def test_raise_if_incorrect_password_raises_when_error_is_visible(self):
        page = FakePage()
        client = OutlookClient(page)

        with self.assertRaisesMessage(LoginFailed, INCORRECT_PASSWORD_ERROR_MESSAGE):
            client.raise_if_incorrect_password()

        error_locator = page.locators[selectors.INCORRECT_PASSWORD_ERROR]
        self.assertEqual(error_locator.waited_for, {'state': 'visible', 'timeout': 5_000})

    def test_raise_if_incorrect_password_returns_when_error_is_absent(self):
        page = FakePage()
        page.locators[selectors.INCORRECT_PASSWORD_ERROR] = FakeLocator(visible=False)
        client = OutlookClient(page)

        client.raise_if_incorrect_password()

        error_locator = page.locators[selectors.INCORRECT_PASSWORD_ERROR]
        self.assertEqual(error_locator.waited_for, {'state': 'visible', 'timeout': 5_000})

    def test_use_password_if_code_prompt_is_shown(self):
        page = FakePage()
        client = OutlookClient(page)

        result = client.use_password_if_code_prompt_is_shown()

        title_locator = page.locators[selectors.GET_CODE_SIGN_IN_TITLE]
        use_password_locator = page.locators[selectors.USE_PASSWORD_BUTTON]

        self.assertTrue(result)
        self.assertEqual(title_locator.waited_for, {'state': 'visible', 'timeout': 8_000})
        self.assertEqual(use_password_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertTrue(use_password_locator.clicked)

    def test_use_password_if_code_prompt_is_shown_returns_false_when_absent(self):
        page = FakePage()
        page.locators[selectors.GET_CODE_SIGN_IN_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        result = client.use_password_if_code_prompt_is_shown()

        self.assertFalse(result)
        self.assertNotIn(selectors.USE_PASSWORD_BUTTON, page.locators)

    def test_decline_stay_signed_in_if_shown(self):
        page = FakePage()
        client = OutlookClient(page)

        result = client.decline_stay_signed_in_if_shown()

        title_locator = page.locators[selectors.STAY_SIGNED_IN_TITLE]
        no_button_locator = page.locators[selectors.STAY_SIGNED_IN_NO_BUTTON]

        self.assertTrue(result)
        self.assertEqual(title_locator.waited_for, {'state': 'visible', 'timeout': 8_000})
        self.assertEqual(no_button_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertTrue(no_button_locator.clicked)

    def test_decline_stay_signed_in_if_shown_returns_false_when_absent(self):
        page = FakePage()
        page.locators[selectors.STAY_SIGNED_IN_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        result = client.decline_stay_signed_in_if_shown()

        self.assertFalse(result)
        self.assertNotIn(selectors.STAY_SIGNED_IN_NO_BUTTON, page.locators)

    def test_skip_protect_account_if_shown(self):
        page = FakePage()
        page.locators[selectors.PROTECT_ACCOUNT_TITLE] = FakeLocator(visible_sequence=[True, False])
        client = OutlookClient(page)

        result = client.skip_protect_account_if_shown()

        title_locator = page.locators[selectors.PROTECT_ACCOUNT_TITLE]
        skip_button_locator = page.locators[selectors.PROTECT_ACCOUNT_SKIP_BUTTON]

        self.assertTrue(result)
        self.assertEqual(title_locator.wait_calls[0], {'state': 'visible', 'timeout': 8_000})
        self.assertEqual(skip_button_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertTrue(skip_button_locator.clicked)
        self.assertEqual(skip_button_locator.click_count, 1)
        self.assertEqual(page.waited_timeout, 1_000)

    def test_skip_protect_account_if_shown_reclicks_when_page_stays_visible(self):
        page = FakePage()
        page.locators[selectors.PROTECT_ACCOUNT_TITLE] = FakeLocator(visible_sequence=[True, True, False])
        client = OutlookClient(page)

        result = client.skip_protect_account_if_shown()

        title_locator = page.locators[selectors.PROTECT_ACCOUNT_TITLE]
        skip_button_locator = page.locators[selectors.PROTECT_ACCOUNT_SKIP_BUTTON]

        self.assertTrue(result)
        self.assertEqual(
            title_locator.wait_calls,
            [
                {'state': 'visible', 'timeout': 8_000},
                {'state': 'visible', 'timeout': 3_000},
                {'state': 'visible', 'timeout': 3_000},
            ],
        )
        self.assertEqual(skip_button_locator.click_count, 2)

    def test_skip_protect_account_if_shown_returns_false_when_absent(self):
        page = FakePage()
        page.locators[selectors.PROTECT_ACCOUNT_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        result = client.skip_protect_account_if_shown()

        self.assertFalse(result)
        self.assertNotIn(selectors.PROTECT_ACCOUNT_SKIP_BUTTON, page.locators)

    def test_choose_outlook_mailbox_layout_if_shown(self):
        page = FakePage()
        client = OutlookClient(page)

        result = client.choose_outlook_mailbox_layout_if_shown()

        title_locator = page.locators[selectors.OUTLOOK_LAYOUT_DIALOG_TITLE]
        mailbox_button_locator = page.locators[selectors.OUTLOOK_LAYOUT_MAILBOX_RECOMMENDED_BUTTON]

        self.assertTrue(result)
        self.assertEqual(title_locator.waited_for, {'state': 'visible', 'timeout': 3_000})
        self.assertEqual(mailbox_button_locator.waited_for, {'state': 'visible', 'timeout': 15_000})
        self.assertTrue(mailbox_button_locator.clicked)
        self.assertEqual(page.waited_timeout, 1_000)

    def test_choose_outlook_mailbox_layout_if_shown_returns_false_when_absent(self):
        page = FakePage()
        page.locators[selectors.OUTLOOK_LAYOUT_DIALOG_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        result = client.choose_outlook_mailbox_layout_if_shown()

        self.assertFalse(result)
        self.assertNotIn(selectors.OUTLOOK_LAYOUT_MAILBOX_RECOMMENDED_BUTTON, page.locators)

    def test_wait_for_successful_login(self):
        page = FakePage()
        client = OutlookClient(page)

        client.wait_for_successful_login()

        self.assertEqual(page.wait_for_function_call['timeout'], 30_000)
        self.assertIn("outlook.live.com", page.wait_for_function_call['expression'])
        self.assertIn("document.title.includes('Outlook')", page.wait_for_function_call['expression'])

    def test_search_for_apple_messages(self):
        page = FakePage()
        client = OutlookClient(page)

        result = client.search_for_apple_messages()

        search_locator = page.locators[selectors.OUTLOOK_SEARCH_INPUT]

        self.assertTrue(result)
        self.assertEqual(search_locator.filled_value, 'Apple')
        self.assertEqual(search_locator.pressed_key, 'Enter')

    def test_open_latest_visible_message(self):
        page = FakePage()
        client = OutlookClient(page)

        result = client.open_latest_visible_message()

        message_locator = page.locators[selectors.OUTLOOK_MESSAGE_ROW]

        self.assertTrue(result)
        self.assertEqual(message_locator.waited_for, {'state': 'visible', 'timeout': 3_000})
        self.assertTrue(message_locator.clicked)
        self.assertEqual(page.waited_timeout, 500)

    def test_extract_latest_apple_otp_from_nearby_text(self):
        otp = extract_latest_apple_otp(
            'Apple\n'
            '123456 is your Apple Account verification code.\n'
            'Other sender\n'
            '999999'
        )

        self.assertEqual(otp, '123456')

    def test_extract_latest_apple_otp_returns_none_without_apple_marker(self):
        otp = extract_latest_apple_otp('Your code is 123456')

        self.assertIsNone(otp)

    def test_find_latest_apple_otp_logs_found_code(self):
        page = FakePage()
        page.locators[selectors.OUTLOOK_LAYOUT_DIALOG_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        with patch.object(client, 'find_latest_apple_otp_once', return_value='123456'):
            with self.assertLogs('apps.scraper.outlook_client', level='INFO') as logs:
                result = client.find_latest_apple_otp(retry_count=3, retry_wait_seconds=10)

        self.assertEqual(result['otp'], '123456')
        self.assertIn('Searching Outlook inbox for Apple OTP on attempt 1 of 4', logs.output[0])
        self.assertIn('Found Apple OTP: 123456 on attempt 1', logs.output[1])

    def test_find_latest_apple_otp_logs_each_search_attempt(self):
        page = FakePage()
        client = OutlookClient(page)

        with patch.object(client, 'choose_outlook_mailbox_layout_if_shown') as mocked_choose_layout:
            with patch.object(client, 'find_latest_apple_otp_once', return_value=None):
                with self.assertLogs('apps.scraper.outlook_client', level='INFO') as logs:
                    result = client.find_latest_apple_otp(retry_count=2, retry_wait_seconds=10)

        self.assertEqual(mocked_choose_layout.call_count, 1)
        self.assertFalse(result['found'])
        self.assertEqual(
            logs.output,
            [
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 1 of 3',
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 2 of 3',
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 3 of 3',
            ],
        )

    def test_find_latest_apple_otp_checks_layout_before_first_search(self):
        page = FakePage()
        client = OutlookClient(page)

        with patch.object(client, 'choose_outlook_mailbox_layout_if_shown') as mocked_choose_layout:
            with patch.object(client, 'find_latest_apple_otp_once', return_value='123456'):
                result = client.find_latest_apple_otp(retry_count=2, retry_wait_seconds=10)

        self.assertEqual(mocked_choose_layout.call_count, 1)
        self.assertEqual(result['otp'], '123456')

    def test_find_latest_apple_otp_logs_each_search_attempt_without_layout_patch(self):
        page = FakePage()
        page.locators[selectors.OUTLOOK_LAYOUT_DIALOG_TITLE] = FakeLocator(visible=False)
        client = OutlookClient(page)

        with patch.object(client, 'find_latest_apple_otp_once', return_value=None):
            with self.assertLogs('apps.scraper.outlook_client', level='INFO') as logs:
                result = client.find_latest_apple_otp(retry_count=2, retry_wait_seconds=10)

        self.assertFalse(result['found'])
        self.assertEqual(
            logs.output,
            [
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 1 of 3',
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 2 of 3',
                'INFO:apps.scraper.outlook_client:[RETRY] Searching Outlook inbox for Apple OTP on attempt 3 of 3',
            ],
        )

    def test_safe_url_removes_query_and_fragment(self):
        url = safe_url('https://outlook.live.com/mail/#code=secret&state=secret')

        self.assertEqual(url, 'https://outlook.live.com/mail/')

    @override_settings(
        OUTLOOK_OTP_RETRY_COUNT=7,
        OUTLOOK_OTP_RETRY_WAIT_SECONDS=12,
        OUTLOOK_OTP_ATTEMPT_TIMEOUT_SECONDS=9,
    )
    def test_otp_retry_config_reads_django_settings(self):
        self.assertEqual(otp_retry_count(), 7)
        self.assertEqual(otp_retry_wait_seconds(), 12)
        self.assertEqual(otp_attempt_timeout_seconds(), 9)

    @override_settings(EMAIL_CHECKS_HEADLESS=False)
    def test_browser_headless_config_reads_django_settings(self):
        self.assertFalse(browser_headless())

    @override_settings(USE_PROXY=False, PROXY_SERVER='http://proxy.example:823')
    def test_browser_proxy_returns_none_when_disabled(self):
        self.assertIsNone(browser_proxy())

    @override_settings(
        USE_PROXY=True,
        PROXY_SERVER='http://proxy.example:823',
        PROXY_USERNAME='proxy-user',
        PROXY_PASSWORD='proxy-password',
    )
    def test_browser_proxy_reads_django_settings(self):
        self.assertEqual(
            browser_proxy(),
            {
                'server': 'http://proxy.example:823',
                'username': 'proxy-user',
                'password': 'proxy-password',
            },
        )

    @override_settings(
        USE_PROXY=True,
        PROXY_SERVER='http://proxy.example:823',
        PROXY_USERNAME='',
        PROXY_PASSWORD='',
    )
    @patch('apps.scraper.browser.Path.exists', return_value=False)
    def test_browser_launch_options_include_proxy(self, mocked_exists):
        self.assertEqual(
            _browser_launch_options(),
            {'proxy': {'server': 'http://proxy.example:823'}},
        )
