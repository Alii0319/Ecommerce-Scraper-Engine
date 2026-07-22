import logging
from decimal import Decimal
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

# Quality gate boundaries — reject prices outside this range.
# Lower bound: prices must be positive (> 0).
# Upper bound: 50,000,000 acts as a sanity ceiling; legitimate retail prices
# should never realistically exceed this value in any currency.
_PRICE_FLOOR = Decimal("0")
_PRICE_CEILING = Decimal("50000000")


def safe_hostname(url: str) -> str:
    try:
        return urlsplit(url).hostname or "unknown"
    except ValueError:
        return "invalid"


def _validate_price(result: ScrapeResult, extractor_name: str, target_url: str) -> ScrapeResult:
    """Apply quality gates to an extracted price. Raises PriceNotFoundError on failure."""
    host = safe_hostname(target_url)

    if result.price <= _PRICE_FLOOR:
        logger.warning(
            "Extracted price failed quality gate: non-positive value",
            extra={
                "extractor": extractor_name,
                "target_host": host,
                "price": str(result.price),
            },
        )
        raise PriceNotFoundError(
            f"Extractor '{extractor_name}' returned a non-positive price ({result.price}); "
            "rejecting as invalid."
        )

    if result.price > _PRICE_CEILING:
        logger.warning(
            "Extracted price failed quality gate: exceeds sanity ceiling",
            extra={
                "extractor": extractor_name,
                "target_host": host,
                "price": str(result.price),
                "ceiling": str(_PRICE_CEILING),
            },
        )
        raise PriceNotFoundError(
            f"Extractor '{extractor_name}' returned a price ({result.price}) above the "
            f"sanity ceiling of {_PRICE_CEILING}; rejecting as likely malformed data."
        )

    return result


def extract_price(html: str, target_url: str = "") -> ScrapeResult:
    soup = BeautifulSoup(html, "lxml")
    attempted: list[str] = []

    for extractor in EXTRACTORS:
        name = extractor.__class__.__name__
        attempted.append(name)

        try:
            result = extractor.extract(soup)
            if result is None:
                continue

            # Apply quality gates before accepting the result.
            validated = _validate_price(result, name, target_url)

            logger.debug(
                "Price extracted successfully",
                extra={
                    "extractor": name,
                    "target_host": safe_hostname(target_url),
                    "price": str(validated.price),
                    "source": validated.source,
                },
            )
            return validated

        except PriceNotFoundError:
            logger.info(
                "Extractor did not find a valid price",
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
