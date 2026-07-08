from django.test import SimpleTestCase
from django.test import override_settings
from unittest.mock import patch

from apps.scraper import selectors
from apps.scraper.config import browser_headless, otp_retry_count, otp_retry_wait_seconds
from apps.scraper.outlook_client import OUTLOOK_LOGIN_URL, OutlookClient, extract_latest_apple_otp, safe_url


class FakeLocator:
    def __init__(self, *, visible=True, text=''):
        self.filled_value = None
        self.waited_for = None
        self.visible = visible
        self.clicked = False
        self.first = self
        self.pressed_key = None
        self.text = text

    def wait_for(self, *, state, timeout):
        if not self.visible:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

            raise PlaywrightTimeoutError('not visible')
        self.waited_for = {'state': state, 'timeout': timeout}

    def fill(self, value):
        self.filled_value = value

    def click(self):
        self.clicked = True

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
        client = OutlookClient(page)

        client.open_login_page()

        self.assertEqual(page.goto_call, {'url': OUTLOOK_LOGIN_URL, 'wait_until': 'domcontentloaded'})

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
        self.assertEqual(message_locator.waited_for, {'state': 'visible', 'timeout': 10_000})
        self.assertTrue(message_locator.clicked)
        self.assertEqual(page.waited_timeout, 2_000)

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
        client = OutlookClient(page)

        with patch.object(client, 'find_latest_apple_otp_once', return_value='123456'):
            with self.assertLogs('apps.scraper.outlook_client', level='INFO') as logs:
                result = client.find_latest_apple_otp(retry_count=3, retry_wait_seconds=10)

        self.assertEqual(result['otp'], '123456')
        self.assertIn('Found Apple OTP: 123456 on attempt 1', logs.output[0])

    def test_safe_url_removes_query_and_fragment(self):
        url = safe_url('https://outlook.live.com/mail/#code=secret&state=secret')

        self.assertEqual(url, 'https://outlook.live.com/mail/')

    @override_settings(OUTLOOK_OTP_RETRY_COUNT=7, OUTLOOK_OTP_RETRY_WAIT_SECONDS=12)
    def test_otp_retry_config_reads_django_settings(self):
        self.assertEqual(otp_retry_count(), 7)
        self.assertEqual(otp_retry_wait_seconds(), 12)

    @override_settings(EMAIL_CHECKS_HEADLESS=False)
    def test_browser_headless_config_reads_django_settings(self):
        self.assertFalse(browser_headless())
