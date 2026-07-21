from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScrapeResult:
    price: Decimal
    currency: str = "PKR"
    is_available: bool = True
    source: str = "generic"
