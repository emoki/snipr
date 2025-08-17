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

That’s it—snipr is now tracking your auction lots. When you want to monitor more items, just add additional `[[item]]` blocks to `snipr.toml` and restart (or let the scheduler reload on the next cycle).


