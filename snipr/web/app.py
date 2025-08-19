from __future__ import annotations
import logging, os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from fasthtml.common import fast_app, Script
from monsterui.all import Theme

from .api import api as api_app
from .ui import add_ui_routes
from .logging_stream import BroadcastHandler, get_log_generator, setup_broadcast_logging
from .scheduler_bridge import (
    ensure_scheduler_started,
    schedule_items_from_settings,
    schedule_items_from_db,
)

if os.getenv("DEBUG_WEB", "0") == "1":
    import debugpy

    debugpy.listen(("0.0.0.0", 5679))
    if os.getenv("DEBUGPY_WAIT", "0") == "1":
        debugpy.wait_for_client()

LOG_LEVEL = os.getenv("SNIPR_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
root_logger = logging.getLogger()
_broadcast = BroadcastHandler()
root_logger.addHandler(_broadcast)
logger = logging.getLogger("snipr_web")


hdrs = Theme.blue.headers() + [
    Script(src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.2/dist/htmx.min.js"),
    Script(src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.3/dist/sse.js"),
]

ui_app, rt = fast_app(hdrs=hdrs)
add_ui_routes(ui_app, rt, _broadcast)

level_name = os.getenv("SNIPR_LOG_LEVEL", "DEBUG").upper()
setup_broadcast_logging(_broadcast, level=getattr(logging, level_name, logging.INFO))


@rt("/logs_stream")
async def get():
    from fasthtml.common import EventStream, sse_message, Article

    logger.info("SSE client connected")  # this should appear in the pane

    async def gen():
        # send a hello immediately so the pane shows something even before logs arrive
        yield sse_message(Article("SSE connected"))
        async for msg in get_log_generator(_broadcast):
            yield msg

    return EventStream(gen())


api = FastAPI(title="snipr API", version="1.0.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api.mount("", api_app)
ui_app.mount("/api", api)


@ui_app.on_event("startup")
async def _startup():
    await ensure_scheduler_started()
    # await schedule_items_from_settings()  # CLI compatibility
    await schedule_items_from_db()  # Web-tracked URLs
    logger.info("snipr web started")


app = ui_app
