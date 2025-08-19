from __future__ import annotations
from urllib.parse import quote
from fasthtml.common import *
from monsterui.all import *

from .scheduler_bridge import track_item, untrack_item
from snipr import db as core_db
from starlette.requests import Request


def _price_cell(row):
    return (
        Span(f"${row.price:,.2f}", cls="badge badge-primary")
        if row
        else Span("—", cls="badge")
    )


def _tracked_items_table():
    rows = []
    for t in core_db.tracked_list(active_only=True):
        latest = core_db.latest_for(t.site, t.url)
        site_q = quote(t.site, safe="")
        url_q = quote(t.url, safe="")
        rows.append(
            Tr(
                Td(t.site.lower()),
                Td(A(t.url, href=t.url, target="_blank")),
                Td(latest.item_title if latest else (t.title or "—")),
                Td(_price_cell(latest)),
                Td(latest.timestamp.isoformat() if latest else "—"),
                Td(
                    Button(
                        "History",
                        cls=ButtonT.secondary,
                        hx_get=f"/history_partial?site={site_q}&url={url_q}",
                        hx_target="#history-pane",
                        hx_swap="innerHTML",
                    ),
                    " ",
                    Button(
                        "Remove",
                        cls=ButtonT.destructive,
                        hx_post=f"/delete_item?site={site_q}&url={url_q}",
                        hx_confirm="Stop tracking this item?",
                        hx_target="#items-pane",
                        hx_swap="innerHTML",
                    ),
                ),
            )
        )
    return Table(
        Thead(
            Tr(
                Td("Site"),
                Td("URL"),
                Td("Title"),
                Td("Latest Price"),
                Td("Seen"),
                Td("Actions"),
            )
        ),
        Tbody(*rows),
        cls="table table-zebra w-full",
        id="items-table",
    )


def _AddItemForm():
    try:
        from snipr.scheduler import SCRAPERS

        sites = sorted(SCRAPERS.keys())
    except Exception:
        sites = ["asi3"]
    return Card(
        H3("Add Item"),
        Form(
            hx_post="/create_item",
            hx_target="#items-pane",
            hx_swap="innerHTML",
            cls="space-y-4",
        )(
            LabelSelect(
                *[Option(s, value=s) for s in sites],
                value="asi3" if "asi3" in sites else sites[0],
                label="Site",
                id="site",
                name="site",
            ),
            LabelInput(
                "URL",
                id="url",
                name="url",
                type="url",
                placeholder="https://…",
                required=True,
            ),
            Button("Add", type="submit", cls=ButtonT.primary),
        ),
    )


def _HistoryPane():
    return Card(H3("History"), Div(id="history-pane", cls="space-y-2"))


def _LogsPane():
    return Card(
        H3("Live Log"),
        Div(
            id="log-stream",
            cls="h-80 overflow-y-auto border rounded-md p-3 bg-base-200 font-mono text-sm",
        ),
        # inline client that appends lines as they arrive
        Script("""
          (function(){
            if (window.__sniprLogES) return;
            var el = document.getElementById('log-stream');
            function append(line){
              var d = document.createElement('div');
              d.textContent = line;
              el.appendChild(d);
              el.scrollTop = el.scrollHeight;
            }
            function start(){
              var es = new EventSource('/logs_stream');
              window.__sniprLogES = es;
              es.onmessage = function(ev){ append(ev.data); };
              es.onerror = function(){ try{ es.close(); }catch(e){}; window.__sniprLogES = null; setTimeout(start, 1500); };
            }
            start();
          })();
          """),
    )


def add_ui_routes(app, rt, broadcast_handler):
    @rt("/")
    def get():
        return Titled(
            Container(
                Div(cls="flex items-center justify-between mb-4")(
                    H1("snipr Dashboard"),
                    A("API Docs", href="/api/docs", target="_blank", cls="link"),
                ),
                Div(cls="flex gap-6")(
                    Div(_AddItemForm(), cls="basis-1/3"),
                    Div(
                        Card(
                            H3("Tracked Items"),
                            Div(id="items-pane")(_tracked_items_table()),
                        ),
                        cls="basis-2/3",
                    ),
                ),
                Div(cls="flex gap-6 mt-6")(
                    Div(_HistoryPane(), cls="basis-1/2"),
                    Div(_LogsPane(), cls="basis-1/2"),
                ),
            ),
        )

    @rt("/history_partial")
    def get(site: str, url: str):
        hist = core_db.history_for(site, url, limit=100)
        if not hist:
            return P("No history yet.")
        return Table(
            Thead(Tr(Td("Time (UTC)"), Td("Price"), Td("Bids"), Td("Currency"))),
            Tbody(*[
                Tr(
                    Td(b.timestamp.isoformat()),
                    Td(f"${b.price:,.2f}"),
                    Td(b.total_bids if b.total_bids is not None else "—"),
                    Td(b.currency or "—"),
                )
                for b in hist
            ]),
            cls="table table-compact w-full",
        )

    @app.post("/create_item")
    async def create_item(request: Request):
        # accept both form and query (robust for HTMX)
        try:
            form = await request.form()
        except Exception:
            form = {}
        site = (form.get("site") or request.query_params.get("site") or "").strip()
        url = (form.get("url") or request.query_params.get("url") or "").strip()
        if not site or not url:
            return P("Missing site or url")
        await track_item(site=site, url=url, fetch_now=True)
        return _tracked_items_table()

    @app.post("/delete_item")
    async def delete_item(request: Request):
        try:
            form = await request.form()
        except Exception:
            form = {}
        site = (form.get("site") or request.query_params.get("site") or "").strip()
        url = (form.get("url") or request.query_params.get("url") or "").strip()
        if not site or not url:
            return P("Missing site or url")
        await untrack_item(site=site, url=url)
        return _tracked_items_table()

    @rt("/__routes__")
    def get():
        paths = [getattr(r, "path", str(r)) for r in app.routes]
        return Pre("\n".join(paths))
