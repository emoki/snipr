# snipr_web/logging_stream.py
from __future__ import annotations
import asyncio, logging
from fasthtml.common import sse_message, Article


class BroadcastHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._qs: set[asyncio.Queue[str]] = set()

    def register(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._qs.add(q)
        return q

    def unregister(self, q: asyncio.Queue[str]):
        self._qs.discard(q)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        for q in list(self._qs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def log(self, msg: str):
        for q in list(self._qs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


async def get_log_generator(handler: BroadcastHandler):
    q = handler.register()
    try:
        while True:
            line = await q.get()
            yield sse_message(Article(line))
    finally:
        handler.unregister(q)
