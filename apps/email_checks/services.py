from apps.scraper.outlook_client import check_outlook_email


def run_outlook_check(
    *,
    email: str,
    password: str,
    max_messages: int,
    headless: bool | None = None,
) -> dict:
    return check_outlook_email(
        email=email,
        password=password,
        max_messages=max_messages,
        headless=headless,
    )
