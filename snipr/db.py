# snipr/db.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import aliased

# TODO(migrations): integrate Alembic here (env.py + versions/). No runtime hacks.


class Bid(SQLModel, table=True):
    __tablename__ = "bid"
    __table_args__ = (
        # Avoid exact duplicates if a poll retries within the same second
        UniqueConstraint("site", "item_url", "timestamp", name="uq_site_url_ts"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # identity
    site: str = Field(index=True)  # e.g., "asi3"
    item_url: str = Field(index=True)
    item_title: str
    lot_number: Optional[str] = Field(default=None, index=True)

    # snapshot
    timestamp: datetime = Field(index=True, description="Snapshot time (UTC)")
    price: float = Field(description="Current bid at timestamp")
    total_bids: Optional[int] = None

    # extra
    currency: str = Field(default="USD", max_length=8)
    sales_tax: Optional[float] = None  # percent, e.g. 7.5
    buyers_premium: Optional[float] = None  # percent, e.g. 18.0


DB_URL = "sqlite:///snipr.sqlite"
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)


def record(snapshot, site: str, item_url: str) -> Bid:
    """Persist one bid snapshot (object must conform to BidSnapshot Protocol)."""
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
            # If uniqueness hit, return existing row
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
            .where(ranked_subq.c.rn <= limit)  # keep top-N
            .order_by(BidAlias.item_title, BidAlias.timestamp.desc())
        )

        return s.exec(stmt).all()
