"""Yoink exception hierarchy."""


class YoinkError(Exception):
    """Base for all yoink errors."""


class TimeoutError(YoinkError):
    """Raised when a page state was not reached within the timeout window."""


class NavigationError(YoinkError):
    """Raised when browser navigation to a URL fails."""


# Backwards-compat alias — will be removed once worker.py is migrated
ScraperError = YoinkError
