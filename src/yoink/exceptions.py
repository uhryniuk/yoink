class NavigationException(Exception):
    pass


class CannotBackException(NavigationException):
    def __init__(self, message: str = "History root reached, cannot go back") -> None:
        super().__init__(message)


class RetrievalException(NavigationException):
    pass


class NoElementException(RetrievalException):
    def __init__(self, message: str = "No element found") -> None:
        super().__init__(message)


class AmbiguousException(RetrievalException):
    def __init__(self, message: str = "Multiple elements could match") -> None:
        super().__init__(message)


class ElementOutOfContextException(RetrievalException):
    def __init__(self, xpath: str, message: str = None) -> None:
        super().__init__(message or f"Element exists but was not in context: {xpath}")


class ScraperError(Exception):
    pass


class NoMorePagesError(Exception):
    """
    Raised when there are no more pages to scrape.

    This is expected behavior and should not be treated as an error,
    but rather a signal to stop the scraping process.
    """

    pass


class DeadPageError(Exception):
    """
    Raised when a page is considered dead, meaning the page no longer exists.
    """

    pass


class ForcerRetryError(Exception):
    """
    Raise this error to force a retry in the scraper when a try block is inside a retry loop.
    """

    pass


class DataError(Exception):
    pass


class ExtractionError(Exception):
    pass


class CliError(Exception):
    def __init__(self, message, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message

    def __str__(self):
        return self.message
