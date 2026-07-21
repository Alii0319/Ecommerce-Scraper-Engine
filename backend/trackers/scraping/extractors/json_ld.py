import json
from typing import Optional
from bs4 import BeautifulSoup

from ..result import ScrapeResult
from .base import BaseExtractor, parse_price_from_text


class JSONLDExtractor(BaseExtractor):
    name: str = "json_ld"

    def extract(self, soup: BeautifulSoup) -> Optional[ScrapeResult]:
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if not script.string:
                continue

            try:
                data = json.loads(script.string)
            except Exception:
                continue

            result = self._parse_schema(data)
            if result:
                return result

        return None

    def _parse_schema(self, data: object) -> Optional[ScrapeResult]:
        if isinstance(data, list):
            for item in data:
                res = self._parse_schema(item)
                if res:
                    return res
            return None

        if not isinstance(data, dict):
            return None

        # Direct Product or Offer
        item_type = str(data.get("@type", ""))
        if "Product" in item_type or "Offer" in item_type:
            offers = data.get("offers")
            if isinstance(offers, dict):
                price = parse_price_from_text(str(offers.get("price") or ""))
                currency = str(offers.get("priceCurrency") or "PKR").upper()
                if price:
                    return ScrapeResult(price=price, currency=currency, source=self.name)
            elif isinstance(offers, list):
                for offer in offers:
                    if isinstance(offer, dict):
                        price = parse_price_from_text(str(offer.get("price") or ""))
                        currency = str(offer.get("priceCurrency") or "PKR").upper()
                        if price:
                            return ScrapeResult(price=price, currency=currency, source=self.name)

            if "price" in data:
                price = parse_price_from_text(str(data.get("price")))
                currency = str(data.get("priceCurrency") or "PKR").upper()
                if price:
                    return ScrapeResult(price=price, currency=currency, source=self.name)

        # Graph structure
        if "@graph" in data and isinstance(data["@graph"], list):
            return self._parse_schema(data["@graph"])

        return None
