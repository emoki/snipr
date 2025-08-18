# snipr_web/scheduler_bridge.py
from __future__ import annotations
import asyncio, base64, logging
from types import SimpleNamespace
from typing import Dict, List

from snipr.scheduler import (
    get_scheduler,
    add_job,
    remove_job,
    JobState,
    _poll_one,  # using your code
)
from snipr.settings import load_settings

log = logging.getLogger("snipr_web.scheduler")

# In-memory registry of tracked items (source of truth = scheduler jobs)
# key: job_id -> {"site": str, "url": str, "state": JobState}
_TRACKED: Dict[str, dict] = {}


def _job_id(site: str, url: str) -> str:
    b = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"{site}:{b}"


async def ensure_scheduler_started():
    sched = await get_scheduler()
    if not sched.running:
        sched.start()
        log.info("APScheduler started")


async def schedule_items_from_settings():
    """On boot, also schedule items listed in settings.item (if any)."""
    settings = load_settings()
    sched = await get_scheduler()
    for idx, item in enumerate(getattr(settings, "item", [])):
        site, url = item.site, item.url
        jid = _job_id(site, url)
        if jid in _TRACKED:
            continue
        state = JobState()
        await add_job(item, settings, state, sched, jid)
        _TRACKED[jid] = {"site": site, "url": url, "state": state}
        log.info("Scheduled from settings: %s %s", site, url)


async def track_item(site: str, url: str, fetch_now: bool = True) -> dict:
    """Add a job via your scheduler.add_job; optionally do an immediate poll."""
    await ensure_scheduler_started()
    settings = load_settings()
    sched = await get_scheduler()

    jid = _job_id(site, url)
    if jid in _TRACKED:
        return {"job_id": jid, "site": site, "url": url, "status": "already-tracked"}

    item_cfg = SimpleNamespace(
        site=site, url=url
    )  # matches your scheduler expectations
    state = JobState()
    await add_job(item_cfg, settings, state, sched, jid)
    _TRACKED[jid] = {"site": site, "url": url, "state": state}

    if fetch_now:
        try:
            await _poll_one(item_cfg, settings, state)  # reuse your logic
        except Exception as e:
            log.warning("Initial fetch failed for %s %s: %s", site, url, e)

    return {"job_id": jid, "site": site, "url": url, "status": "scheduled"}


async def untrack_item(site: str, url: str) -> bool:
    """Remove the job via your scheduler.remove_job."""
    sched = await get_scheduler()
    jid = _job_id(site, url)
    await remove_job(jid, sched)
    removed = _TRACKED.pop(jid, None) is not None
    return removed


def list_tracked() -> List[dict]:
    """Return a lightweight list of currently scheduled items."""
    return [
        {"job_id": jid, "site": v["site"], "url": v["url"]}
        for jid, v in sorted(_TRACKED.items())
    ]
