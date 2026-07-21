class ScrapeError(Exception):
    """Base exception for expected scraper failures."""


class UnsafeTargetUrlError(ScrapeError):
    """Raised when URL fails public safety / SSRF checks."""


class ExtractorError(ScrapeError):
    """Base exception for extractor level failures."""


class PriceNotFoundError(ExtractorError):
    """Raised when no trustworthy price can be extracted."""


class UnsupportedPageError(ExtractorError):
    """Raised when page content structure is unsupported by an extractor."""


class MalformedStructuredDataError(ExtractorError):
    """Raised when structured data (JSON-LD, microdata) cannot be parsed."""
