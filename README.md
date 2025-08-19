## snipr

Follow these steps and you’ll have bid tracking running in a couple of minutes.

---

### 1 · Prerequisites

| Tool                        | Why you need it                                                                                     |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| **Python ≥ 3.12**           | Core runtime                                                                                        |
| **uv**                      | Fast dependency & venv manager ([https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)) |
| *(Optional)* **Playwright** | For JS-heavy auction pages—installed later                                                          |

---

### 2 · Clone or download snipr

```bash
git clone https://github.com/your-org/snipr.git
cd snipr
```

---

### 3 · Create and activate a virtual env

```bash
uv venv .venv -p 3.12
source .venv/bin/activate
```

---

### 4 · Install snipr (editable)

```bash
uv pip install -e .            # core dependencies
# for Playwright fallback scraping: (not currently used)
uv pip install -e ".[browser]"
playwright install             # downloads headless Chromium etc.
```

---

### 5 · Set up configuration

1. **Copy the sample file**

   ```bash
   cp snipr.example.toml snipr.toml
   ```

2. **Edit `snipr.toml`**

   ```toml
   [polling]
   min_seconds = 30        # lower bound of random interval
   max_seconds = 60        # upper bound
   end_grace_seconds = 60  # stop after 60 s of no bid change

   [[item]]
   url  = "https://online.asi3auctions.com/…/lot-details/8ff7d327…"
   site = "asi3"           # must match a key in SCRAPERS dict

   # Add as many [[item]] blocks as you like
   ```

---

### 6 · Start tracking

```bash
snipr start
```

You’ll see log lines such as:

```
snipr started – Ctrl+C to quit
12:05:17 INFO snipr – 2023 FORD BRONCO SPORT → $10,250.00
```

snipr polls each URL at a random time between `min_seconds` and `max_seconds`.
If the price hasn’t changed for `end_grace_seconds`, that lot’s job is removed.

---

### 7 · Inspect recent snapshots

```bash
snipr ls --site asi3 --limit 5
```

Shows the **5 most-recent rows per item** for site *ASI3*.

---

### 8 · Browse the database (optional)

`snipr.sqlite` is an ordinary SQLite file. Open it in **DBeaver**, **SQLite Browser**, or any SQL client to run full queries.


---

## 9 · Web UI (FastAPI + MonsterUI)
uv pip install -e .
The web server provides a dashboard to **add/remove tracked URLs**, view **current prices & history**, and a **live log**. It also exposes a small JSON API.

### Install web UI deps

If you didn’t already install them, add:

```bash
uv pip install fastapi uvicorn fasthtml monsterui apscheduler
```

> If you use Docker, see the **Docker** section below.

### Start the web server

```bash
uvicorn snipr.web.app:app --reload --port 8000
```

Open: [http://localhost:8000](http://localhost:8000)

* **Dashboard** at `/`
* **API docs** at `/api/docs`

### How scheduling works (CLI vs Web)

* **CLI** (unchanged): the scheduler is populated from **`snipr.toml`** (`[[item]]` entries).
* **Web UI**: tracked URLs are stored in a dedicated **`Tracked`** table and scheduled on server startup.
* Both can coexist; jobs are deduplicated by a stable job id derived from `(site, url)`.
* Removing an item in the UI **marks it inactive** in `Tracked` (history remains) and stops the job.

### Database tables

* **`Bid`** – immutable snapshots (what you already had).
* **`Tracked`** – web-managed URLs:

  * `id`, `site`, `url`, `title?`, `active` (bool), `created_at`, `updated_at`
  * Removing an item sets `active = False` (soft delete). History remains in `Bid`.

### Using the dashboard

* **Add Item**: select a site and paste the item URL; the server schedules it and triggers an initial fetch.
* **Tracked Items**: shows site, URL, last title, latest price, last seen time.
* **History**: click “History” to view the last snapshots for that item.
* **Remove**: stops the job and marks the row inactive.

### Live Log pane

* Streams Python logger output (e.g., `snipr`, `uvicorn`, `apscheduler`, `httpx`).
* Uses Server-Sent Events. If empty, see **Troubleshooting** below.

### JSON API

Base path: `/api`

* `GET /api/tracked` → list tracked (active) items:

  ```json
  [{"site":"asi3","url":"https://…"}]
  ```
* `POST /api/tracked` → add & schedule:

  ```json
  { "site": "asi3", "url": "https://…" }
  ```
* `DELETE /api/tracked?site=asi3&url=https%3A%2F%2F…` → untrack & stop job
* `GET /api/latest?site=asi3&url=…` → latest `Bid` snapshot for that item
* `GET /api/history?site=asi3&url=…&limit=100` → newest-first history
* `GET /api/recent?limit_per_item=1&max_items=50` → recent latest rows across items

### Environment variables (optional)

* `SNIPR_LOG_LEVEL` – `INFO` (default) or `DEBUG`
* `CORS_ALLOW_ORIGINS` – comma-separated list for API access (default `*`)
* `DEBUG_WEB=1` – enable debugpy on port `5679` (see `snipr/web/app.py`)
* `DEBUGPY_WAIT=1` – make the server wait for debugger attach


---

## 10 · Docker (optional)

A simple container setup is included:

```bash
docker build -t snipr-web:latest .
docker run --rm -it -p 8000:8000 snipr-web:latest
# or with compose
# docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).


---

That’s it—snipr is now tracking your auction lots. When you want to monitor more items, just add additional `[[item]]` blocks to `snipr.toml` and restart (or let the scheduler reload on the next cycle).
