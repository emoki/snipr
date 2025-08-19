# snipr/web/logging_stream.py
from __future__ import annotations
import asyncio, logging
from typing import Iterable
from fasthtml.common import sse_message, Article


class BroadcastHandler(logging.Handler):
    """Logging handler that fans out log lines to connected SSE clients."""

    def __init__(self):
        super().__init__()
        self._qs: set[asyncio.Queue[str]] = set()

    def register(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._qs.add(q)
        # Show something immediately so we know SSE is connected
        try:
            q.put_nowait("log stream connected")
        except asyncio.QueueFull:
            pass
        return q

    def unregister(self, q: asyncio.Queue[str]):
        self._qs.discard(q)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        for q in list(self._qs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # drop oldest until we can insert (simple backpressure)
                try:
                    _ = q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass

    def log(self, msg: str):
        # Manual push convenience (not via logging module)
        for q in list(self._qs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


async def get_log_generator(handler: BroadcastHandler):
    """Yield proper SSE chunks as plain text lines."""
    q = handler.register()
    try:
        while True:
            line = await q.get()
            # send plain text so the client can set textContent safely
            yield sse_message(line)
    finally:
        handler.unregister(q)


def setup_broadcast_logging(handler: BroadcastHandler, level: int = logging.INFO):
    """
    Attach `handler` to the root logger *and* common non-propagating loggers.
    Uvicorn loggers (uvicorn, uvicorn.error, uvicorn.access) default to propagate=False.
    """
    handler.setLevel(logging.NOTSET)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s -- %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(fmt)

    # Root
    root = logging.getLogger()
    root.setLevel(level)
    if handler not in root.handlers:
        root.addHandler(handler)

    # Libraries that often disable propagation:
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "snipr",
        "apscheduler",
        "httpx",
    ):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        # attach directly; don't rely on propagation
        if handler not in lg.handlers:
            lg.addHandler(handler)
        # keep their existing console handlers too; do not set propagate True to avoid duplicates
