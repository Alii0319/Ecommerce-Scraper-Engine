from typing import Optional
from bs4 import BeautifulSoup

from ..result import ScrapeResult
from .base import BaseExtractor, parse_price_from_text


class GenericExtractor(BaseExtractor):
    name: str = "generic"

    def extract(self, soup: BeautifulSoup) -> Optional[ScrapeResult]:
        visible_selectors = (
            '[itemprop="price"]',
            ".price-item--sale",
            ".price--special",
            ".pdp-price",
            ".pdp-product-price",
            ".sale-price",
            ".current-price",
            ".price",
        )

        for selector in visible_selectors:
            node = soup.select_one(selector)
            if not node:
                continue

            price = parse_price_from_text(node.get_text(" ", strip=True))
            if price is not None:
                return ScrapeResult(price=price, currency="PKR", source=self.name)

        return None
