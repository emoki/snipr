"""Snipr WebUI (MonsterUI + FastAPI)

Run:

    uvicorn snipr.webui.main:app --reload

This WebUI uses snipr/db.py for all data access (Tracked + Bid).
CLI continues to use snipr.toml; the WebUI stores tracked URLs in DB.
"""

from __future__ import annotations
import base64
import os
from typing import List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fasthtml.common import *
from monsterui.all import *

# Use db.py only
from snipr import db as core_db


# ----------------------- (optional) debugpy attach ----------------------------
if os.getenv("DEBUG_WEBUI", "0") == "1":
    import debugpy

    debugpy.listen(("0.0.0.0", 5680))
    if os.getenv("DEBUGPY_WAIT", "0") == "1":
        debugpy.wait_for_client()


# ----------------------------- helpers ---------------------------------------
def _key(site: str, url: str) -> str:
    """URL-safe key for (site, url) so we can have a clean route param."""
    raw = f"{site}||{url}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unkey(key: str) -> Tuple[str, str]:
    pad = "=" * (-len(key) % 4)  # restore removed '=' padding
    raw = base64.urlsafe_b64decode((key + pad).encode("ascii")).decode("utf-8")
    site, url = raw.split("||", 1)
    return site, url


# ------------------------------ UI bits --------------------------------------
def _items_table():
    """Render tracked items (from Tracked) with latest Bid snapshot if present."""
    rows = []
    tracked = core_db.tracked_list(active_only=True)
    for t in tracked:
        latest = core_db.latest_for(t.site, t.url)
        title = latest.item_title if latest else (t.title or t.url)
        price = f"${latest.price:,.2f}" if latest else "—"
        seen = latest.timestamp.strftime("%Y-%m-%d %H:%M:%S") if latest else "—"
        rows.append(
            Tr(
                Td(
                    A(
                        title,
                        href=f"/items/{_key(t.site, t.url)}",
                        cls="hover:underline text-primary",
                    )
                ),
                Td(price),
                Td(t.site),
                Td(seen),
                Td(
                    A("Open", href=t.url, target="_blank", cls="link"),
                ),
            )
        )

    return Table(
        Thead(
            Tr(
                Td("Title"),
                Td("Current Price"),
                Td("Site"),
                Td("Last Updated"),
                Td("Link"),
            )
        ),
        Tbody(*rows) if rows else Tbody(Tr(Td("No tracked items yet.", colSpan=5))),
        cls="table w-full",
    )


def _add_item_form():
    try:
        from snipr.scheduler import SCRAPERS

        sites = sorted(SCRAPERS.keys())
    except Exception:
        sites = ["asi3"]
    default_site = "asi3" if "asi3" in sites else (sites[0] if sites else "")

    return Form(
        LabelSelect(
            *[Option(s, value=s) for s in sites],
            label="Site",
            id="site",
            name="site",
            value=default_site,
        ),
        LabelInput(
            "Auction URL",
            id="url",
            name="url",
            type="url",
            placeholder="https://example.com/item",
            required=True,
        ),
        Button("Add", cls=ButtonT.primary),
        action="/items",
        method="post",
        cls="space-y-2",
    )


def _history_table(site: str, url: str):
    hist = core_db.history_for(site, url, limit=100)
    if not hist:
        return P("No history yet.")
    return Table(
        Thead(Tr(Td("Time (UTC)"), Td("Price"), Td("Bids"), Td("Currency"))),
        Tbody(*[
            Tr(
                Td(b.timestamp.isoformat(timespec="seconds")),
                Td(f"${b.price:,.2f}"),
                Td(b.total_bids if b.total_bids is not None else "—"),
                Td(b.currency or "—"),
            )
            for b in hist
        ]),
        cls="table table-compact w-full",
    )


# ------------------------------ App + routes ---------------------------------
headers = Theme.blue.headers()
app, rt = fast_app(hdrs=headers)


@rt
def index():
    return Titled(
        "Snipr Dashboard",
        Container(
            Card(H3("Tracked Items"), _items_table()),
            H2("Add Item"),
            _add_item_form(),
            cls="space-y-6",
        ),
    )


@rt
def items(key: str):
    """Item detail page keyed by base64(site||url)."""
    site, url = _unkey(key)
    latest = core_db.latest_for(site, url)
    title = latest.item_title if latest else url
    return Titled(
        title,
        Card(
            H3("Current Price", cls=TextPresets.bold_sm),
            P(f"${latest.price:,.2f}") if latest else P("—"),
            H3("Price History", cls="mt-4"),
            _history_table(site, url),
            Div(cls="mt-4")(
                A("Open original", href=url, target="_blank", cls="link"),
                " · ",
                A("Back", href="/", cls="link"),
            ),
        ),
    )


@app.post("/items")
async def add_item_endpoint(request: Request):
    """Add a tracked URL via DB; CLI snipr.toml is not touched here."""
    data = await request.form()
    url = (data.get("url") or "").strip()
    site = (data.get("site") or "").strip()
    if not url or not site:
        return RedirectResponse("/", status_code=303)
    try:
        core_db.tracked_add(site=site, url=url)
        # Optionally: trigger scheduling here if desired
        # from snipr.web.scheduler_bridge import track_item
        # await track_item(site, url, fetch_now=True)
    except Exception as exc:
        # Keep UX smooth; consider flashing this via session in a fuller app
        print("Error adding item:", exc)
    return RedirectResponse("/", status_code=303)
