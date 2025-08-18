import logging
from logging.handlers import RotatingFileHandler
from typing import Annotated
import os
import typer
from snipr.scheduler import main as run
from snipr.db import latest_items_for_site

if os.getenv("DEBUG_CLI", "0") == "1":
    import debugpy

    debugpy.listen(("0.0.0.0", 5679))
    if os.getenv("DEBUGPY_WAIT", "0") == "1":
        debugpy.wait_for_client()


# ---------------------------------------------------------------------------
# Global logging configuration - set once at import time
# ---------------------------------------------------------------------------
LOG_LEVEL = logging.DEBUG if os.getenv("SNIPR_DEBUG", "0") == "1" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler = RotatingFileHandler(
    "./snipr.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)

root = logging.getLogger()  # root logger
root.addHandler(file_handler)


app = typer.Typer(help="snipr CLI")


@app.command()
def start():
    """Run the poller."""
    run()


@app.command()
def ls(
    site: Annotated[str, typer.Option("--site", "-s", help="Site code (e.g. 'ASI3')")],
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Number of rows per item.")
    ] = 20,
):
    """Show recent snapshots."""
    rows = latest_items_for_site(site.lower(), limit=limit)
    for row in rows:
        print(
            f"{row.timestamp:%H:%M:%S} | {row.item_title[:40]:40} | ${row.price:,.2f}"
        )


if __name__ == "__main__":
    app()
