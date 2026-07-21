from bs4 import BeautifulSoup

from .exceptions import PriceNotFoundError
from .extractors import (
    DarazExtractor,
    GenericExtractor,
    JSONLDExtractor,
    ShopifyExtractor,
)
from .result import ScrapeResult

EXTRACTORS = [
    JSONLDExtractor(),
    ShopifyExtractor(),
    DarazExtractor(),
    GenericExtractor(),
]


def extract_price(html: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "lxml")

    for extractor in EXTRACTORS:
        try:
            result = extractor.extract(soup)
            if result is not None:
                return result
        except Exception:
            continue

    raise PriceNotFoundError("No supported price source was found")
