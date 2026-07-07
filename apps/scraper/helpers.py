# apps/scraper/services/apple/helpers.py
import logging
import random
import string
from datetime import datetime
from typing import Type

from playwright.async_api import FrameLocator
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


def wait_and_fill(frame: FrameLocator, selector: str, value: str, label: str, timeout: int = 30000, ) -> None:
    logger.info(f"[STEP] Waiting for {label}...")

    locator = frame.locator(selector)
    locator.wait_for(state="visible", timeout=timeout)

    logger.info(f"[SUCCESS] {label} found")

    locator.fill(value)

    logger.info(f"[SUCCESS] {label} filled")


def human_pause(page, min_ms: int = 150, max_ms: int = 600) -> None:
    """Idle for a random short span, mimicking human hesitation between actions."""
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def human_move_to(page, locator) -> None:
    """Move the mouse to a random point inside the element instead of teleporting to it."""
    box = locator.bounding_box()
    if not box:
        return

    x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
    y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
    page.mouse.move(x, y, steps=random.randint(15, 35))


def human_click(page, locator, label: str = "element", timeout: int = 30000, force: bool = False) -> None:
    logger.info(f"[STEP] Waiting for {label}...")
    locator.wait_for(state="visible", timeout=timeout)
    locator.scroll_into_view_if_needed()

    human_move_to(page, locator)
    human_pause(page, 80, 300)

    logger.info(f"[STEP] Clicking {label}...")
    locator.click(delay=random.randint(30, 120), force=force)

    logger.info(f"[SUCCESS] {label} clicked")


def human_type(page, locator, text: str, min_delay: int = 45, max_delay: int = 160,
               mistake_chance: float = 0.06) -> None:
    """Type text one character at a time with randomized delays and occasional typos+corrections."""
    for char in text:
        if char.isalpha() and random.random() < mistake_chance:
            typo = random.choice(string.ascii_lowercase)
            locator.type(typo, delay=random.randint(min_delay, max_delay))
            human_pause(page, 80, 220)
            locator.press("Backspace")
            human_pause(page, 60, 180)

        locator.type(char, delay=random.randint(min_delay, max_delay))

        if random.random() < 0.05:
            human_pause(page, 200, 700)


def wait_and_type(frame: FrameLocator, selector: str, value: str, label: str, timeout: int = 30000):
    logger.info(f"[STEP] Waiting for {label}...")
    input_box = frame.locator(selector)
    input_box.wait_for(state="visible", timeout=timeout)
    logger.info(f"[SUCCESS] {label} found")

    human_click(frame, input_box, label, timeout)

    dummy_chars = ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 9)))
    human_type(frame, input_box, dummy_chars)

    human_pause(frame, 150, 450)
    input_box.press("Control+A")
    human_pause(frame, 60, 180)
    input_box.press("Backspace")
    human_pause(frame, 150, 400)

    human_type(frame, input_box, value)
    logger.info(f"[SUCCESS] {label} filled by typing method")


def wait_and_click_last(frame: FrameLocator, selector: str, label: str, timeout: int = 30000, ) -> None:
    logger.info(f"[STEP] Selecting last matching {label}...")

    locator = frame.locator(selector).last
    human_click(frame, locator, label, timeout)


def wait_and_click_first(frame: FrameLocator, selector: str, label: str, timeout: int = 30000, ) -> None:
    logger.info(f"[STEP] Selecting first matching {label}...")

    locator = frame.locator(selector).first
    locator.highlight()
    human_click(frame, locator, label, timeout)


def click_and_switch_tab(page, selector, label, timeout=15000):
    with page.context.expect_page() as page_info:
        wait_and_click_last(page, selector, label, timeout=timeout)

    new_page = page_info.value
    new_page.wait_for_load_state("domcontentloaded")

    return new_page


def click_and_switch_tab_if_opened(page, selector, label, timeout=15000):
    try:
        with page.context.expect_page(timeout=timeout) as page_info:
            wait_and_click_last(page, selector, label, timeout=timeout)

        new_page = page_info.value
        # new_page.wait_for_load_state("domcontentloaded")

        return new_page
    except PlaywrightTimeoutError as e:
        logger.error(f"[STEP] error : {e}")
        page.wait_for_load_state("domcontentloaded")
        return page


async def get_text(frame: FrameLocator, selector: str, label: str, timeout: int = 30000, ) -> str:
    logger.info(f"[STEP] Reading {label}...")

    try:
        locator = frame.locator(selector)
        await locator.wait_for(state="visible", timeout=timeout)

        text = (await locator.inner_text(timeout=timeout)).strip()

        logger.info(f"[INFO] {label}: {text}")
        return text

    except PlaywrightTimeoutError:
        logger.info(f"[ERROR] Could not find visible {label} with selector: {selector}")
        raise


def get_visible_error_text_by_selector(page, selector: str, timeout: int = 3000) -> str | None:
    try:
        locator = page.locator(selector, timeout=timeout)
        # create timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # build filename
        filename = f"message_{timestamp}.png"
        locator.screenshot(path=filename)

        locator.wait_for(state="visible", timeout=timeout)

        error_text = locator.inner_text().strip()

        if error_text:
            logger.info(f"[ERROR] Error found => {error_text}")

        return error_text or None

    except PlaywrightTimeoutError:

        return None


def check_for_email_availability_error(raised_error_text: str | None, expected_error_text: str, ) -> bool:
    if not raised_error_text or raised_error_text is None:
        logger.info("[OK] Provided email is available")
        return False

    logger.info(f"[STEP] Checking for recommended emails: {expected_error_text}")
    if expected_error_text in raised_error_text:
        logger.info(f"[STEP] Provided email is not available choosing from recommended emails")
        return True


def check_for_error_text_match(raised_error_text: str | None, expected_error_text: str, raise_exception: bool = True,
                               exception_class: Type[Exception] = None, ) -> bool:
    if not raised_error_text or raised_error_text is None:
        logger.info(f"[OK] No Errors found for {expected_error_text}")
        return False

    logger.info(f"[STEP] Checking for error match => '{expected_error_text}' vs '{raised_error_text}'")
    if expected_error_text in raised_error_text:
        logger.info(f"[ERROR] Raising Exception => {raised_error_text}")
        if raise_exception:
            raise exception_class(raised_error_text)
        return True
