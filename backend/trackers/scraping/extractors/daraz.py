from typing import Optional
from bs4 import BeautifulSoup

from ..result import ScrapeResult
from .base import BaseExtractor, parse_price_from_text


class DarazExtractor(BaseExtractor):
    name: str = "daraz"

    def extract(self, soup: BeautifulSoup) -> Optional[ScrapeResult]:
        selectors = (
            "span.pdp-price",
            ".pdp-product-price",
            '[data-automation="product-price"]',
        )

        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue

            price = parse_price_from_text(node.get_text(" ", strip=True))
            if price is not None:
                return ScrapeResult(price=price, currency="PKR", source=self.name)

        return None
