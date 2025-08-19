# snipr_web/scheduler_bridge.py
from __future__ import annotations
import base64, logging
from types import SimpleNamespace
from typing import Dict, List

from snipr.scheduler import get_scheduler, add_job, remove_job, JobState, _poll_one
from snipr.settings import load_settings
from snipr import db as core_db

log = logging.getLogger("snipr_web.scheduler")

# In-memory map of scheduled jobs to avoid double-scheduling
# key = job_id, value = {"site": str, "url": str, "state": JobState}
_SCHEDULED: Dict[str, dict] = {}


def _job_id(site: str, url: str) -> str:
    b = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"{site}:{b}"


async def ensure_scheduler_started():
    sched = await get_scheduler()
    if not sched.running:
        sched.start()
        log.info("APScheduler started")


async def schedule_items_from_settings():
    """CLI compatibility: keep scheduling settings.item (unchanged)."""
    settings = load_settings()
    sched = await get_scheduler()
    for item in getattr(settings, "item", []):
        site, url = item.site, item.url
        jid = _job_id(site, url)
        if jid in _SCHEDULED:
            continue
        state = JobState()
        await add_job(item, settings, state, sched, jid)
        _SCHEDULED[jid] = {"site": site, "url": url, "state": state}
        log.info("Scheduled from settings: %s %s", site, url)


async def schedule_items_from_db():
    """Web server: schedule all active tracked items from DB."""
    sched = await get_scheduler()
    settings = load_settings()
    for t in core_db.tracked_list(active_only=True):
        site, url = t.site, t.url
        jid = _job_id(site, url)
        if jid in _SCHEDULED:
            continue
        item_cfg = SimpleNamespace(site=site, url=url)
        state = JobState()
        await add_job(item_cfg, settings, state, sched, jid)
        _SCHEDULED[jid] = {"site": site, "url": url, "state": state}
        log.info("Scheduled from db.tracked: %s %s", site, url)


async def track_item(site: str, url: str, fetch_now: bool = True) -> dict:
    """Persist in DB (active) and schedule if not already running."""
    await ensure_scheduler_started()
    core_db.tracked_add(site, url)  # DB is source of truth

    settings = load_settings()
    sched = await get_scheduler()
    jid = _job_id(site, url)
    if jid not in _SCHEDULED:
        item_cfg = SimpleNamespace(site=site, url=url)
        state = JobState()
        await add_job(item_cfg, settings, state, sched, jid)
        _SCHEDULED[jid] = {"site": site, "url": url, "state": state}
        if fetch_now:
            try:
                await _poll_one(item_cfg, settings, state)
            except Exception as e:
                log.warning("Initial fetch failed for %s %s: %s", site, url, e)
    return {"job_id": jid, "site": site, "url": url, "status": "scheduled"}


async def untrack_item(site: str, url: str) -> bool:
    """Mark inactive in DB and remove job if scheduled."""
    ok = core_db.tracked_remove(site, url)
    sched = await get_scheduler()
    jid = _job_id(site, url)
    try:
        await remove_job(jid, sched)
    except Exception:
        pass
    removed = _SCHEDULED.pop(jid, None) is not None
    return ok or removed


def list_tracked() -> List[dict]:
    """Return active tracked items from DB (for API convenience)."""
    return [
        {"site": t.site, "url": t.url} for t in core_db.tracked_list(active_only=True)
    ]
