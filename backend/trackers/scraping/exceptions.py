class ScrapeError(Exception):
    """Base exception for expected scraper failures."""


class PriceNotFoundError(ScrapeError):
    """Raised when no trustworthy price can be extracted."""


class UnsafeTargetUrlError(ScrapeError):
    """Raised when URL fails public safety / SSRF checks."""
