from contextlib import contextmanager
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from apps.scraper.config import browser_headless, browser_proxy


@contextmanager
def chromium_page(*, headless: bool | None = None):
    resolved_headless = browser_headless() if headless is None else headless

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=resolved_headless,
            **_browser_launch_options(),
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            yield page
        finally:
            context.close()
            browser.close()


def _browser_launch_options() -> dict:
    options = {}
    proxy = browser_proxy()
    if proxy:
        options['proxy'] = proxy

    executable_path = os.getenv('PLAYWRIGHT_BROWSER_EXECUTABLE')
    if executable_path:
        options['executable_path'] = executable_path
        return options

    channel = os.getenv('PLAYWRIGHT_BROWSER_CHANNEL')
    if channel:
        options['channel'] = channel
        return options

    chrome_path = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    if chrome_path.exists():
        options['executable_path'] = str(chrome_path)
        return options

    edge_path = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    if edge_path.exists():
        options['executable_path'] = str(edge_path)
        return options

    return options
