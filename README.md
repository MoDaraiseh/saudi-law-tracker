# saudi-law-tracker

Scrapes and tracks regulatory publications from Saudi government sources, diffing
each run so you only get told about what is genuinely new.

## Sources tracked

Configured in [`config/sources.yaml`](config/sources.yaml). Defaults:

| Key | Source | Notes |
| --- | --- | --- |
| `bureau_of_experts` | Bureau of Experts at the Council of Ministers — laws.boe.gov.sa | Consolidated laws & regulations, Hijri issue dates |
| `sama_circulars` | Saudi Central Bank (SAMA) | Rules & circulars — **currently down site-side, not a scraper bug; see below** |
| `zatca_updates` | Zakat, Tax and Customs Authority (ZATCA) | Tax rulings, regulations, public consultations |
| `citc` | Communications, Space & Technology Commission (CST/CITC) | Regulations & consultations |
| `mhrsd_labor` | Ministry of Human Resources & Social Development | Labor System + ministerial-decision amendments |
| `umm_al_qura` | Umm Al-Qura official gazette — uqn.gov.sa | Weekly gazette issues |

Add, disable, or remove sources by editing the YAML — set `enabled: false` to
pause one without losing its config.

**Known limitation:** `sama_circulars` has returned a fake shell page instead
of real API/JSON responses since at least 2026-09-14 (last re-confirmed live
2026-09-16), across every inner path on sama.gov.sa, in both languages —
confirmed via infrastructure-header analysis distinguishing it from genuine
SharePoint responses, not just content inspection. This looks like a
site-side outage or in-progress migration, not a selector bug here — see the
full investigation in [`scrapers/sama.py`](src/saudi_law_tracker/scrapers/sama.py)'s
module docstring. Re-check periodically rather than assuming a scraper fix
here is what's needed; `saudi-law-tracker status` correctly reports it as
`error` in the meantime.

## Layout

```
config/sources.yaml            registry of what to scrape
src/saudi_law_tracker/
  config.py                    settings (.env) + source loading
  models.py                    RegulatoryDocument, ScrapeResult
  http.py                      polite retrying async HTTP client
  storage.py                   SQLite doc store + raw HTML snapshots + run state
  pipeline.py                  orchestration: scrape -> persist -> diff -> notify
  notify.py                    optional Slack-compatible webhook
  cli.py                       `saudi-law-tracker` command
  scrapers/
    base.py                    BaseScraper + @register registry
    _common.py                 GenericListingScraper, link harvester
    <source>.py                one module per source
data/
  raw/<source>/                timestamped HTML snapshots
  regulations.db               SQLite: one `regulations` table, all sources
  state/runs.json              last-run status per source
tests/
```

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on POSIX
pip install -e ".[dev]"
cp .env.example .env             # then edit
```

## Usage

```bash
saudi-law-tracker sources                 # list sources + scraper wiring
saudi-law-tracker scrape                  # scrape all enabled sources
saudi-law-tracker scrape -s zatca_updates -s citc
saudi-law-tracker scrape --dry-run        # parse but don't persist
saudi-law-tracker status                  # last-run + doc counts
saudi-law-tracker export zatca_updates -n 10

saudi-law-tracker query --sector labor            # across all sources, no SQL
saudi-law-tracker query -t law -t regulation --since 2024-01-01
saudi-law-tracker query -q "القيمة المضافة" --json  # machine-readable, for agents
```

`query` filters the `regulations` table: `--source`, `--type` (doc_type),
`--sector` (substring of source key or category), `--text` (title/summary),
`--since` / `--until` (Gregorian publication date), `--limit`, `--json`.

`status --max-age-hours N` additionally flags (prints `STALE` next to, and
exits non-zero if any exist) an *enabled* source whose last successful run
is older than `N` hours, or that has never run at all — meant for a
scheduled job to alert on, so a source silently failing for days doesn't go
unnoticed:

```bash
saudi-law-tracker status --max-age-hours 36   # exit 0 if every enabled source ran in the last 36h
```

## Scheduling

The daily job is: run `scrape`, run `status --max-age-hours 36` so a source
that's stopped scraping successfully gets flagged rather than just silently
going quiet, then run the live smoke test (`pytest -m live
tests/test_live_smoke.py`) as a second, independent check that every enabled
source still returns at least one verified, dated row against the *live*
site — not just a fixture. `scrape.cmd` at the repo root already does all
three, in order, appending output to `logs\cron.log` and exiting non-zero if
any of them failed (so Task Scheduler's "Last Run Result" reflects any of
the three).

### Windows Task Scheduler

1. Confirm `scrape.cmd` runs cleanly by hand first: `.\scrape.cmd` from the
   repo root, then check `logs\cron.log` for `STALE` / errors.
2. Open Task Scheduler → **Create Task…** (not *Basic Task*, so you get the
   full options below).
3. **General** tab: name it (e.g. `saudi-law-tracker daily scrape`); select
   **Run whether user is logged on or not**; check **Run with highest
   privileges** only if your `.venv`/network setup actually needs it (it
   usually doesn't).
4. **Triggers** tab → **New…** → Daily, pick a time (e.g. 06:00), **Enabled**.
5. **Actions** tab → **New…** → Action: *Start a program*; **Program/script**:
   the full path to `scrape.cmd` (e.g.
   `C:\Users\<you>\saudi-law-tracker\scrape.cmd`); **Start in**: the repo root
   (e.g. `C:\Users\<you>\saudi-law-tracker`) — `scrape.cmd` also `cd /d`s
   there itself, but setting it here too avoids surprises if the task is ever
   invoked with a different working directory.
6. **Conditions**/**Settings** tabs: on a laptop, uncheck "Start the task only
   if the computer is on AC power" unless that's genuinely what you want.
7. Save. To verify: right-click the task → **Run**, then check
   `logs\cron.log` and the task's **Last Run Result** column (`0x0` =
   success; anything else = the scrape failed or a source is stale).

Equivalent one-liner via `schtasks` (run as the user who should own the
task, from an elevated prompt only if you also chose "highest privileges"
above):

```powershell
schtasks /Create /TN "saudi-law-tracker daily scrape" /TR "C:\Users\<you>\saudi-law-tracker\scrape.cmd" /SC DAILY /ST 06:00 /RL LIMITED
```

### cron (Linux/macOS)

`status` and the smoke test should run even if `scrape` itself failed, and
the redirect needs to wrap the whole compound command (not just the last
part) to capture all three:

```
0 6 * * *  { cd /path/to/saudi-law-tracker && .venv/bin/saudi-law-tracker scrape ; .venv/bin/saudi-law-tracker status --max-age-hours 36 ; .venv/bin/pytest -m live tests/test_live_smoke.py ; } >> logs/cron.log 2>&1
```

## Adding a scraper

Each source's scraper starts from `GenericListingScraper`, which fetches every
`start_path`, snapshots the HTML under `data/raw/`, and emits candidate links
via a generic harvester — so a new source produces *something* on day one.

To make it accurate, override `discover()` with real selectors. Each scraper
module's docstring records what is known about that portal's markup / JSON
endpoints and carries `TODO(selectors)` notes.

```python
@register("my_source")            # must match `scraper:` in sources.yaml
class MySourceScraper(BaseScraper):
    async def discover(self):
        resp = await self.http.get(self.abs_url(self.source.start_paths[0]))
        self.store.write_raw(self.source.key, "index", resp.text)
        for row in HTMLParser(resp.text).css(".law-card"):
            yield RegulatoryDocument(...)
```

## Notes

- Dates from Saudi sources are usually Hijri; `utils/dates.py` converts them and
  handles Arabic-Indic digits.
- A document's identity is `source + URL + publication date`. Re-scraping an
  unchanged page is a no-op; a substantive edit at the same date is reported as
  *changed*; the same URL re-published under a new date is a *new* entry.
- `utils/text.py` normalizes Arabic (alef/ya/ta-marbuta, diacritics, tatweel)
  for dedupe — display text is kept as-is.
- Be a good citizen: `SLT_REQUEST_DELAY` throttles per host, the client sends a
  descriptive User-Agent, and `HttpClient` fetches and caches each host's
  `robots.txt` (once per run) and skips any disallowed path, logging a
  `robots.disallowed` warning instead of fetching it. A `robots.txt` that
  itself fails to load is treated as "disallow everything" for that host
  rather than assumed permissive. This doesn't replace actually reading each
  site's terms of use, which `robots.txt` alone doesn't cover.
