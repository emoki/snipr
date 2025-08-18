from __future__ import annotations
import logging, os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from fasthtml.common import fast_app, Script
from monsterui.all import Theme

from .api import api as api_app
from .ui import add_ui_routes
from .logging_stream import BroadcastHandler, get_log_generator
from .scheduler_bridge import ensure_scheduler_started, schedule_items_from_settings


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

hdrs = Theme.blue.headers()
ui_app, rt = fast_app(hdrs=hdrs)
add_ui_routes(ui_app, rt, _broadcast)


@rt("/logs_stream")  # <- make SSE path explicit
async def get():
    from fasthtml.common import EventStream

    async def gen():
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
    await schedule_items_from_settings()
    logger.info("snipr web started")


app = ui_app
