# saudi-law-tracker

Scrapes and tracks regulatory publications from Saudi government sources, diffing
each run so you only get told about what is genuinely new.

## Sources tracked

Configured in [`config/sources.yaml`](config/sources.yaml). Defaults:

| Key | Source | Notes |
| --- | --- | --- |
| `bureau_of_experts` | Bureau of Experts at the Council of Ministers — laws.boe.gov.sa | Consolidated laws & regulations, Hijri issue dates |
| `sama_circulars` | Saudi Central Bank (SAMA) | Rules & circulars |
| `zatca_updates` | Zakat, Tax and Customs Authority (ZATCA) | Tax rulings, regulations, public consultations |
| `citc` | Communications, Space & Technology Commission (CST/CITC) | Regulations & consultations |
| `mhrsd_labor` | Ministry of Human Resources & Social Development | Labor System + ministerial-decision amendments |
| `umm_al_qura` | Umm Al-Qura official gazette — uqn.gov.sa | Weekly gazette issues |

Add, disable, or remove sources by editing the YAML — set `enabled: false` to
pause one without losing its config.

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

Run on a schedule with cron / Task Scheduler:

```
0 6 * * *  cd /path/to/saudi-law-tracker && .venv/bin/saudi-law-tracker scrape
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
- Be a good citizen: `SLT_REQUEST_DELAY` throttles per host, and the client sends
  a descriptive User-Agent. Check each site's terms and `robots.txt`.
