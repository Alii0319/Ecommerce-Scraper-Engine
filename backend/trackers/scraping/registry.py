import logging
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

from .exceptions import (
    PriceNotFoundError,
    UnsupportedPageError,
    MalformedStructuredDataError,
)
from .extractors import (
    DarazExtractor,
    GenericExtractor,
    JSONLDExtractor,
    ShopifyExtractor,
)
from .result import ScrapeResult

logger = logging.getLogger(__name__)

EXTRACTORS = [
    JSONLDExtractor(),
    ShopifyExtractor(),
    DarazExtractor(),
    GenericExtractor(),
]


def safe_hostname(url: str) -> str:
    try:
        return urlsplit(url).hostname or "unknown"
    except Exception:
        return "invalid"


def extract_price(html: str, target_url: str = "") -> ScrapeResult:
    soup = BeautifulSoup(html, "lxml")
    attempted: list[str] = []

    for extractor in EXTRACTORS:
        name = extractor.__class__.__name__
        attempted.append(name)

        try:
            result = extractor.extract(soup)
            if result is not None:
                return result
        except PriceNotFoundError:
            logger.info(
                "Extractor did not find a price",
                extra={"extractor": name, "target_host": safe_hostname(target_url)},
            )
            continue
        except UnsupportedPageError:
            continue
        except MalformedStructuredDataError:
            logger.warning(
                "Extractor encountered malformed product data",
                extra={"extractor": name, "target_host": safe_hostname(target_url)},
            )
            continue
        except Exception:
            logger.exception(
                "Unexpected extractor failure",
                extra={"extractor": name, "target_host": safe_hostname(target_url)},
            )
            raise

    raise PriceNotFoundError(f"No supported price source was found. Attempted: {attempted}")
