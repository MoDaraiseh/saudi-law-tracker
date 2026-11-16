# saudi-law-tracker

Scrapes and tracks regulatory publications from Saudi government sources, diffing
each run so you only get told about what is genuinely new.

## Current status (16 Nov 2026)

Scrapers exist for all six sources below; three return data today. Re-checked
live from my network on 16 Nov 2026 with `saudi-law-tracker scrape --dry-run`:

| Source | Status | Detail |
| --- | --- | --- |
| `zatca_updates` | working | 59 documents found |
| `mhrsd_labor` | working | 34 documents found |
| `umm_al_qura` | working | 24 documents found |
| `bureau_of_experts` | unreachable from my network | Connections fail; last successful scrape 7 Nov 2026. It has worked only on some days since mid-September. Not yet known whether this is a network block or the site being down. |
| `citc` | unreachable from my network | Same pattern; last successful scrape 7 Nov 2026. |
| `sama_circulars` | site down | The site returns an error page instead of data, as it has since 14 Sep 2026 (see below). |

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

**Known limitation:** `sama_circulars` has returned an error page instead
of real API/JSON responses since at least 2026-09-14 (last re-checked live
2026-11-16, in both languages). The September investigation found the same
page on every inner path on sama.gov.sa, and confirmed via
infrastructure-header analysis that it is not a genuine SharePoint response. This looks like a
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
  state/runs.json              last run + last successful run per source
tests/
```

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on POSIX
pip install -e ".[dev]"
cp .env.example .env             # Windows cmd: copy .env.example .env -- then edit,
                                 # at least the contact address in SLT_HTTP_USER_AGENT
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

`status` prints each source's last run, its status (`ok`/`error`) and `last_ok`,
the last run that ended `ok` (`never` if none has; `unknown` for a source whose
only record predates `last_ok` tracking and whose latest run failed).
`status --max-age-hours N` additionally flags (prints `STALE` next to, and
exits non-zero if any exist) an *enabled* source whose last successful run
is older than `N` hours, or that has never run at all — meant for a
scheduled job to alert on, so a source silently failing for days doesn't go
unnoticed:

```bash
saudi-law-tracker status --max-age-hours 36   # exit 0 if every enabled source ran in the last 36h
```

## Example output

Real output from 16 Nov 2026. `saudi-law-tracker status`:

```
bureau_of_experts    docs=  538 last_run=2026-11-16T12:42:49.569964+00:00 error last_ok=2026-11-07T12:33:38.803647+00:00
sama_circulars       docs=    0 last_run=2026-11-16T12:42:34.104033+00:00 error last_ok=unknown
zatca_updates        docs=   70 last_run=2026-11-16T12:44:32.832261+00:00 ok    last_ok=2026-11-16T12:44:32.832261+00:00
citc                 docs=   40 last_run=2026-11-16T12:42:49.561049+00:00 error last_ok=2026-11-07T12:33:40.181791+00:00
mhrsd_labor          docs=   82 last_run=2026-11-16T12:42:38.853311+00:00 ok    last_ok=2026-11-16T12:42:38.853311+00:00
umm_al_qura          docs=   50 last_run=2026-11-16T12:42:45.173999+00:00 ok    last_ok=2026-11-16T12:42:45.173999+00:00
```

`docs=` counts every row stored so far, which is why it is higher than one
scrape's `found=` count. `saudi-law-tracker query --source umm_al_qura --limit 1 --json`:

```json
[
  {
    "uid": "760a7f8e9859c7f8",
    "source_key": "umm_al_qura",
    "title": "جريدة أم القرى - العدد 5195",
    "title_en": null,
    "doc_type": "gazette_issue",
    "url": "https://www.uqn.gov.sa/digital?date=2026-11-13",
    "pdf_urls": [
      "https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/11/13/ummalqura_pdf-20261113-1.pdf&ts=042659"
    ],
    "reference_number": "5195",
    "summary": null,
    "published_gregorian": "2026-11-13",
    "published_hijri": null,
    "effective_date": null,
    "last_modified": null,
    "categories": [
      "gazette_issue"
    ],
    "raw_html_path": null,
    "content_hash": "e0d9b3326e4f90746e19cb6f047f23c5fcdfe4b68a9d738749b0f462a219dc27",
    "first_seen": "2026-11-14T11:52:30.108101Z",
    "last_seen": "2026-11-16T12:42:44.841576Z",
    "verified": true
  }
]
```

## Scheduling

Run it daily with `scrape.cmd` (Windows) or one cron line (Linux/macOS): scrape,
then `status --max-age-hours 36` and the live smoke test, so a source that stops
working is flagged. Setup steps for both: [docs/SCHEDULING.md](docs/SCHEDULING.md).

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
- `.env` is read from the project root wherever the command runs from (a `.env` in the
  current directory, if any, overrides it), and a relative `SLT_DATA_DIR` such as
  `./data` is resolved against the project root too, so a scheduled task or a
  run from another folder always uses the same database.
- Be a good citizen: `SLT_REQUEST_DELAY` throttles per host, the client sends a
  descriptive User-Agent, and `HttpClient` fetches and caches each host's
  `robots.txt` (once per run) and skips any disallowed path, logging a
  `robots.disallowed` warning instead of fetching it. A `robots.txt` that
  itself fails to load is treated as "disallow everything" for that host
  rather than assumed permissive. This doesn't replace actually reading each
  site's terms of use, which `robots.txt` alone doesn't cover.
