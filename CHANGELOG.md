# Changelog

Notable changes, newest first, by commit date. There are no tagged releases
yet; the package version is 0.1.0. Assessment findings, and how each one was
verified, are in [docs/ASSESSMENT_LOG.md](docs/ASSESSMENT_LOG.md).

## Unreleased

- README: a dated current-status table for the six sources.
- The assessment record moved from this file to `docs/ASSESSMENT_LOG.md`;
  this file is now a conventional changelog.
- Agent evals: only the latest report is kept, as
  `evals/agent/latest_report.json`; earlier runs remain in git history.
- README: scheduling steps moved to `docs/SCHEDULING.md`; real `status` and
  `query --json` output added.
- `ruff` in the dev extras is bounded to `>=0.17,<0.18`, so a new ruff release
  can't break CI unannounced. Adds a CI badge and a `.mailmap`.
- A weekly, informational live smoke test on GitHub Actions
  (`.github/workflows/live.yml`). Sources listed in `SLT_LIVE_KNOWN_DOWN` are
  expected failures; only a working source that fails turns it red.

## 2026-11-14

- CI actions pinned to full commit SHAs; Dependabot keeps them updated.

## 2026-11-13

- Fresh installs work with selectolax 1.0: all scrapers use the lexbor
  backend.
- CI: ruff, mypy and the offline tests on Ubuntu and Windows, Python 3.11 and
  3.13.

## 2026-10-21

- `status` shows each source's last successful run (`last_ok`), and
  `status --max-age-hours` judges staleness on it, so a source that fails
  every day is flagged.
- A document repeated within one scrape no longer aborts the run; a storage
  error marks only that source as `error`.
- `.env` and a relative `SLT_DATA_DIR` resolve against the project root, not
  the current directory.
- `runs.json` is written atomically; `query`/`export --limit` must be at
  least 1.

## 2026-09-16

- Agent evals: a second independent judged run confirmed a 0.0% judged
  hallucination rate.
- The refusal scorer recognises two more refusal phrasings.
- The SAMA outage is documented in `scrapers/sama.py` and the README.

## 2026-09-15

- Agent evals: corrected stale premises in `hallucination.yaml`, and added
  the `--judge` LLM-graded pass for the hallucination suite.

## 2026-09-14

- Scrapers tuned against the live portals, with a `verified` field on every
  row and detail-page enrichment for the Bureau of Experts.
- Staleness check, scheduling script and live smoke test.
- Publication dates kept separate from page `last_modified` timestamps, and a
  dynamic list of verified sources.
- robots.txt handling, certifi, and the MIT license.

## 2026-09-13

- Initial version: six configured sources, SQLite storage with run diffs,
  and the `saudi-law-tracker` CLI.
