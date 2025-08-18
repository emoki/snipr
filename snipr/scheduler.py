import asyncio, random, logging, httpx, time
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from snipr.settings import load_settings
from snipr.core import AuctionFinished
from snipr.fetchers.asi3 import Asi3Auction
from snipr.db import record

log = logging.getLogger("snipr")

# Map site code → scraper class
SCRAPERS = {
    "asi3": Asi3Auction,
    # "ebay": EbayAuction,
}


class JobState:
    def __init__(self):
        self.last_price: float | None = None
        self.last_change: float = time.time()


async def _poll_one(item_cfg, settings, state: JobState):
    scraper_cls = SCRAPERS[item_cfg.site]
    scraper = scraper_cls()

    try:
        snap = await scraper.fetch(
            item_cfg.url,
            headers=settings.random_headers(),
            proxy=settings.random_proxy(),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (429, 503):
            back = settings.network.retry_backoff_seconds
            await asyncio.sleep(back + random.uniform(0, back))
        log.warning("%s failed: %s", item_cfg.url, exc)
        return

    # store + console print
    record(snap, site=item_cfg.site.upper(), item_url=item_cfg.url)
    log.info("%s → $%.2f", snap.item_title, snap.current_price)

    # detect change / end-of-auction
    if state.last_price is None or snap.current_price != state.last_price:
        state.last_price = snap.current_price
        state.last_change = time.time()
    elif time.time() - state.last_change >= settings.polling.end_grace_seconds:
        log.info(
            "No new bids for %s seconds – stopping %s",
            settings.polling.end_grace_seconds,
            snap.item_title,
        )
        raise AuctionFinished


async def _schedule_all():
    settings = load_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    states: dict[str, JobState] = {}

    def make_wrapper(item, state, job_id):
        async def wrapper():
            try:
                await _poll_one(item, settings, state)
            except AuctionFinished:
                log.info("Stopping job %s", job_id)
                scheduler.remove_job(job_id)
                if not scheduler.get_jobs():
                    log.info("No more jobs – shutting down")
                    scheduler.shutdown(wait=False)

        return wrapper

    for idx, item in enumerate(settings.item):
        state = states[item.url] = JobState()
        # random initial delay so all jobs don't fire together
        delay = random.uniform(0, settings.polling.min_seconds)

        job_id = f"lot-{idx}"
        scheduler.add_job(
            make_wrapper(item, state, job_id),
            "interval",
            seconds=settings.polling.min_seconds,
            jitter=settings.polling.max_seconds - settings.polling.min_seconds,
            next_run_time=datetime.utcnow() + timedelta(seconds=delay),
            id=job_id,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=30,
        )

    scheduler.start()
    print("snipr started – Ctrl+C to quit")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(_schedule_all())
