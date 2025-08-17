"""
ASI 3 Auctions scraper – fully populated BidSnapshot.

Extracts:
  • item_title        (e.g. "2023 FORD BRO...")
  • lot_number        (e.g. "10020")
  • current_price     (float)
  • currency          (e.g. "USD")
  • sales_tax         (percentage, 7.50 -> 7.5)
  • buyers_premium    (percentage, 18   -> 18.0)
  • total_bids        (int)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from snipr.core import AuctionSite, BidSnapshot, BidParseError

# --------------------------------------------------------------------------- #
#  Selectors & regex helpers
# --------------------------------------------------------------------------- #

_TITLE_SEL = ["h1.lot-title", ".lot-title h1", "h1[itemprop='name']"]
_LOTNUM_SEL = [".lot-number", ".lot__number", "span:contains('Lot')"]
_PRICE_SEL = [".current-bid", ".asking-bid", ".lot-bid span"]
_BIDS_SEL = [".bid-count", ".bidding-history-count", "span:contains('bids')"]

_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")
_PRICE_RE = re.compile(r"\$?\s*([0-9][\d,]*\.?\d{0,2})")
_LOTNUM_RE = re.compile(r"\bLOT(?:\s+No\.)?\s*#?\s*([A-Za-z0-9-]+)")
_BIDS_RE = re.compile(r"\b([0-9]+)\s*bids?\b", re.I)
_CURRENCY_RE = re.compile(r"(USD|GBP|EUR|CAD|AUD)")


# --------------------------------------------------------------------------- #
#  Dataclass
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Snap:
    timestamp: datetime
    item_title: str
    lot_number: str
    currency: str
    current_price: float
    sales_tax: float
    buyers_premium: float
    total_bids: int


# --------------------------------------------------------------------------- #
#  Scraper
# --------------------------------------------------------------------------- #


class Asi3Auction(AuctionSite):
    """BidSpotter / ASI3 timed-lot scraper."""

    async def fetch(
        self,
        item_url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        proxy: Optional[str] = None,
    ) -> BidSnapshot:
        html = await self._get_html(item_url, headers=headers, proxy=proxy)
        snap = self._parse(html)
        if snap is None:
            raise BidParseError("Page structure changed – selectors failed")
        return snap

    # ---------------- HTTP ---------------- #

    async def _get_html(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]],
        proxy: Optional[str],
    ) -> str:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30,
            headers=headers,
            proxy=proxy,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    # --------------- PARSE ---------------- #

    def _parse(self, html: str) -> Optional[BidSnapshot]:
        soup = BeautifulSoup(html, "html.parser")
        body_text = soup.get_text(" ", strip=True)

        lot_number = self._first_text(soup, _LOTNUM_SEL) or self._first_match(
            _LOTNUM_RE, body_text
        )
        item_title = (
            self._first_text(soup, _TITLE_SEL) or soup.title.contents[0]
            if soup.title
            else None
        )

        price_txt = self._first_text(soup, _PRICE_SEL)
        bids_txt = self._first_text(soup, _BIDS_SEL) or body_text

        # --- mandatory fields ------------------------------------------------
        if not (item_title and lot_number and price_txt):
            return None

        price = float(_PRICE_RE.search(price_txt).group(1).replace(",", ""))
        currency = (
            _CURRENCY_RE.search(price_txt) or _CURRENCY_RE.search(body_text) or ["USD"]
        )[0]

        # --- optional fields -------------------------------------------------
        sales_tax = self._percent_near_label(body_text, "Sales tax")
        buyers_premium = self._percent_near_label(body_text, "Buyer's premium")
        total_bids = (
            int(_BIDS_RE.search(bids_txt).group(1)) if _BIDS_RE.search(bids_txt) else 0
        )

        return _Snap(
            timestamp=datetime.utcnow(),
            item_title=item_title,
            lot_number=lot_number,
            currency=currency,
            current_price=price,
            sales_tax=sales_tax,
            buyers_premium=buyers_premium,
            total_bids=total_bids,
        )

    # ------------ small helpers ---------- #
    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: list[str]) -> Optional[str]:
        for sel in selectors:
            node = soup.select_one(sel)
            if node and (txt := node.get_text(" ", strip=True)):
                return txt
        return None

    @staticmethod
    def _first_match(regex: re.Pattern, *candidates) -> Optional[str]:
        for cand in candidates:
            if not cand:
                continue
            m = regex.search(str(cand))
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _search(text: str, regex: re.Pattern) -> Optional[str]:
        m = regex.search(text)
        return m.group(1).strip() if m else None

    def _percent_near_label(self, text: str, label: str) -> float:
        """
        Extract “label: 7.50%” → 7.5
        Return 0.0 if not found.
        """
        idx = 0
        for _ in range(3):
            idx = (
                text[idx + len(label) :].lower().find(label.lower()) + idx + len(label)
            )
            if idx == -1:
                return 0.0
            segment = text[idx : idx + 60]  # slice near the label
            m = _PERCENT_RE.search(segment)
            if m and m.group(1):
                return float(m.group(1)) if m else 0.0
