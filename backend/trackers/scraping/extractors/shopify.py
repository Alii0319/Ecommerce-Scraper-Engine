from typing import Optional
from bs4 import BeautifulSoup

from ..result import ScrapeResult
from .base import BaseExtractor, parse_price_from_text


class ShopifyExtractor(BaseExtractor):
    name: str = "shopify"

    def extract(self, soup: BeautifulSoup) -> Optional[ScrapeResult]:
        meta_selectors = (
            'meta[property="product:price:amount"]',
            'meta[property="og:price:amount"]',
            'meta[name="twitter:data1"]',
            '[itemprop="price"][content]',
        )

        for selector in meta_selectors:
            node = soup.select_one(selector)
            if not node:
                continue

            candidate = node.get("content") or node.get("value")
            price = parse_price_from_text(candidate)
            if price is None:
                continue

            currency_node = (
                soup.select_one('meta[property="product:price:currency"]')
                or soup.select_one('[itemprop="priceCurrency"]')
            )
            currency = "PKR"
            if currency_node:
                currency = (
                    currency_node.get("content")
                    or currency_node.get_text(strip=True)
                    or "PKR"
                ).upper()

            return ScrapeResult(price=price, currency=currency, source=self.name)

        return None
