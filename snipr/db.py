# snipr/db.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Tuple

from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import aliased

from snipr.settings import SNIPR_ROOT

# TODO(migrations): integrate Alembic here (env.py + versions/). No runtime hacks.


class Bid(SQLModel, table=True):
    __tablename__ = "bid"
    __table_args__ = (
        UniqueConstraint("site", "item_url", "timestamp", name="uq_site_url_ts"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    site: str = Field(index=True)  # e.g., "asi3"
    item_url: str = Field(index=True)
    item_title: str
    lot_number: Optional[str] = Field(default=None, index=True)
    timestamp: datetime = Field(index=True, description="Snapshot time (UTC)")
    price: float = Field(description="Current bid at timestamp")
    total_bids: Optional[int] = None
    currency: str = Field(default="USD", max_length=8)
    sales_tax: Optional[float] = None
    buyers_premium: Optional[float] = None


# NEW: Tracked URLs for the web server
class Tracked(SQLModel, table=True):
    __tablename__ = "tracked"
    __table_args__ = (UniqueConstraint("site", "url", name="uq_tracked_site_url"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    url: str = Field(index=True)
    title: Optional[str] = None
    active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())


DB_URL = f"sqlite:////{SNIPR_ROOT}/data/snipr.sqlite"
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)


def record(snapshot, site: str, item_url: str) -> Bid:
    row = Bid(
        site=site,
        item_url=item_url,
        timestamp=snapshot.timestamp,
        item_title=snapshot.item_title,
        lot_number=getattr(snapshot, "lot_number", None),
        currency=snapshot.currency,
        price=snapshot.current_price,
        sales_tax=getattr(snapshot, "sales_tax", None),
        buyers_premium=getattr(snapshot, "buyers_premium", None),
        total_bids=getattr(snapshot, "total_bids", None),
    )
    with Session(engine) as s:
        s.add(row)
        try:
            s.commit()
        except Exception:
            s.rollback()
            existing = s.exec(
                select(Bid).where(
                    Bid.site == site,
                    Bid.item_url == item_url,
                    Bid.timestamp == snapshot.timestamp,
                )
            ).first()
            if existing:
                return existing
            raise
        s.refresh(row)
        return row


def latest_items_for_site(site: str, limit: int = 10) -> list[Bid] | None:
    with Session(engine) as s:
        ranked_subq = (
            select(
                Bid,
                func.row_number()
                .over(partition_by=Bid.item_title, order_by=Bid.timestamp.desc())
                .label("rn"),
            )
            .where(Bid.site == site)
            .subquery()
        )
        BidAlias = aliased(Bid, ranked_subq)
        stmt = (
            select(BidAlias)
            .where(ranked_subq.c.rn <= limit)
            .order_by(BidAlias.item_title, BidAlias.timestamp.desc())
        )
        return s.exec(stmt).all()


def latest_for(site: str, url: str) -> Optional[Bid]:
    with Session(engine) as s:
        stmt = (
            select(Bid)
            .where(Bid.site == site, Bid.item_url == url)
            .order_by(Bid.timestamp.desc())
            .limit(1)
        )
        return s.exec(stmt).first()


def history_for(site: str, url: str, limit: int = 100) -> list[Bid]:
    with Session(engine) as s:
        stmt = (
            select(Bid)
            .where(Bid.site == site, Bid.item_url == url)
            .order_by(Bid.timestamp.desc())
            .limit(limit)
        )
        return s.exec(stmt).all()


def recent_latest(limit_per_item: int = 1, max_items: int = 50) -> list[Bid]:
    with Session(engine) as s:
        ranked = select(
            Bid,
            func.row_number()
            .over(partition_by=(Bid.site, Bid.item_url), order_by=Bid.timestamp.desc())
            .label("rn"),
        ).subquery()
        BidAlias = aliased(Bid, ranked)
        base = select(BidAlias).where(ranked.c.rn <= limit_per_item)
        stmt = base.order_by(BidAlias.timestamp.desc())
        rows = s.exec(stmt).all()
        if max_items and limit_per_item >= 1:
            out: list[Bid] = []
            seen_items: set[tuple[str, str]] = set()
            groups = 0
            for r in rows:
                key = (r.site, r.item_url)
                if key not in seen_items:
                    if groups >= max_items:
                        break
                    seen_items.add(key)
                    groups += 1
                out.append(r)
            return out
        return rows


# ---- Tracked helpers for the Web UI/API ------------------------------------


def tracked_add(site: str, url: str, title: Optional[str] = None) -> Tracked:
    now = datetime.utcnow()
    with Session(engine) as s:
        existing = s.exec(
            select(Tracked).where(Tracked.site == site, Tracked.url == url)
        ).first()
        if existing:
            existing.active = True
            if title:
                existing.title = title
            existing.updated_at = now
            s.add(existing)
            s.commit()
            s.refresh(existing)
            return existing
        row = Tracked(
            site=site, url=url, title=title, active=True, created_at=now, updated_at=now
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def tracked_remove(site: str, url: str) -> bool:
    """Soft-remove: mark inactive so history remains; scheduler will stop job."""
    now = datetime.utcnow()
    with Session(engine) as s:
        row = s.exec(
            select(Tracked).where(Tracked.site == site, Tracked.url == url)
        ).first()
        if not row:
            return False
        if not row.active:
            return True
        row.active = False
        row.updated_at = now
        s.add(row)
        s.commit()
        return True


def tracked_list(active_only: bool = True) -> List[Tracked]:
    with Session(engine) as s:
        stmt = select(Tracked)
        if active_only:
            stmt = stmt.where(Tracked.active == True)  # noqa: E712
        stmt = stmt.order_by(Tracked.created_at.desc())
        return s.exec(stmt).all()
