import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup
from ..result import ScrapeResult


def parse_price_from_text(text: str | None) -> Optional[Decimal]:
    if not text:
        return None

    normalized = text.replace("\u00a0", " ").replace(",", "").strip()
    matches = re.findall(r"(?<!\d)(\d+(?:\.\d{1,2})?)(?!\d)", normalized)

    for raw_value in matches:
        try:
            value = Decimal(raw_value)
        except InvalidOperation:
            continue

        if value > 0:
            return value

    return None


class BaseExtractor(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, soup: BeautifulSoup) -> Optional[ScrapeResult]:
        pass
