# snipr_web/api.py
from __future__ import annotations
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, HttpUrl

from snipr import db as core_db
from .scheduler_bridge import list_tracked, track_item, untrack_item

api = FastAPI(
    title="snipr API", version="1.0.0", docs_url="/docs", openapi_url="/openapi.json"
)


class ItemIn(BaseModel):
    site: str
    url: HttpUrl


class TrackedItem(BaseModel):
    site: str
    url: HttpUrl


class BidOut(BaseModel):
    site: str
    item_url: HttpUrl
    item_title: str
    timestamp: str
    price: float
    currency: Optional[str] = None
    total_bids: Optional[int] = None
    lot_number: Optional[str] = None


def _to_bid_out(b) -> BidOut:
    return BidOut(
        site=b.site,
        item_url=b.item_url,
        item_title=b.item_title,
        timestamp=b.timestamp.isoformat(),
        price=b.price,
        currency=b.currency,
        total_bids=b.total_bids,
        lot_number=b.lot_number,
    )


@api.get("/tracked", response_model=List[TrackedItem])
def tracked():
    return list_tracked()


@api.post("/tracked", response_model=TrackedItem, status_code=201)
async def add_tracked(payload: ItemIn):
    await track_item(payload.site, str(payload.url), fetch_now=True)
    return TrackedItem(site=payload.site, url=payload.url)


@api.delete("/tracked", status_code=204)
async def delete_tracked(site: str, url: HttpUrl):
    ok = await untrack_item(site, str(url))
    if not ok:
        raise HTTPException(404, "Not currently tracked")


@api.get("/latest", response_model=Optional[BidOut])
def latest(site: str, url: HttpUrl):
    row = core_db.latest_for(site, str(url))
    return _to_bid_out(row) if row else None


@api.get("/history", response_model=List[BidOut])
def history(site: str, url: HttpUrl, limit: int = Query(100, ge=1, le=1000)):
    rows = core_db.history_for(site, str(url), limit=limit)
    return [_to_bid_out(r) for r in rows]


@api.get("/recent", response_model=List[BidOut])
def recent(
    limit_per_item: int = Query(1, ge=1, le=5), max_items: int = Query(50, ge=1, le=500)
):
    rows = core_db.recent_latest(limit_per_item=limit_per_item, max_items=max_items)
    return [_to_bid_out(r) for r in rows]
