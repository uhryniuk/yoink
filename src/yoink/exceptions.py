class NavigationException(Exception):
    """Raised when a browser navigation operation fails."""


class CannotBackException(NavigationException):
    """Raised when the browser history is at root and cannot go back."""

    def __init__(self, message: str = "History root reached, cannot go back") -> None:
        super().__init__(message)


class ScraperError(Exception):
    """Base class for general scraping errors."""


class RetrievalException(ScraperError):
    """Raised when an element cannot be retrieved from the page."""


class NoElementException(RetrievalException):
    """Raised when no element matches the given selector."""

    def __init__(self, message: str = "No element found") -> None:
        super().__init__(message)


class AmbiguousException(RetrievalException):
    """Raised when multiple elements match a selector that expected one."""

    def __init__(self, message: str = "Multiple elements could match") -> None:
        super().__init__(message)


class ElementOutOfContextException(RetrievalException):
    """Raised when an element exists on the page but is outside the target context."""

    def __init__(self, xpath: str, message: str | None = None) -> None:
        super().__init__(message or f"Element exists but was not in context: {xpath}")


class NoMorePagesError(Exception):
    """Signal that pagination is exhausted. Not a true error — stop iteration on this."""


class DeadPageError(ScraperError):
    """Raised when a page no longer exists or is unrecoverable."""


class ForceRetryError(ScraperError):
    """Raise to force a retry when inside a tenacity retry block."""


class DataError(Exception):
    """Raised when extracted data is malformed or unexpected."""


class ExtractionError(ScraperError):
    """Raised when content extraction from a page fails."""
