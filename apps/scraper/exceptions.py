class OutlookScraperError(Exception):
    """Base error for Outlook browser automation failures."""


class LoginFailed(OutlookScraperError):
    pass


class MfaRequired(OutlookScraperError):
    pass


class ScraperTimeout(OutlookScraperError):
    pass


class OutlookHighDemand(OutlookScraperError):
    pass
