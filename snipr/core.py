from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol


class BidSnapshot(Protocol):
    timestamp: datetime
    item_title: str
    lot_number: str
    currency: str
    current_price: float
    sales_tax: float
    buyers_premium: float
    total_bids: int


class BidParseError(RuntimeError):
    """Raised when mandatory price data cannot be extracted from the HTML/DOM."""


class AuctionFinished(Exception):
    """Raised when we decide a lot is done."""


class AuctionSite(ABC):
    """A pluggable scraper/bid reader."""

    @abstractmethod
    async def fetch(self, item_url: str) -> BidSnapshot: ...

    # Optional: hook for CAPTCHA / auth early-login
    async def warm_up(self) -> None: ...
