# Changelog / final-state summary

This is not a conventional release changelog — it's a durable record of every
finding from the technical assessment(s) run against this project, what its
real current status is, and how that status was actually verified (not just
asserted). Written 2026-09-16, purely for a future reader's benefit (very
possibly the same person who wrote it) six months from now, asking "did we
actually fix this, and how do I know." Update this file's table whenever a
finding's status changes; don't let it go stale into a false record.

Three status categories, and it matters which one a finding is in:

- **Closed, verified** — a real fix, confirmed against live behavior, not just
  code review or a git log entry. Safe to treat as done.
- **Confirmed live limitation, no fix available** — investigated to a
  definitive root cause, and the root cause is outside this codebase's
  control (a third-party site is down, or the data genuinely isn't there).
  Not "not done" — genuinely not fixable from here. Re-check periodically;
  don't re-diagnose it from scratch each time.
- **Partial / open** — real, non-zero progress, but a real gap remains. Says
  exactly what's still missing.

## Summary table

| Finding | Status | What actually verifies it |
|---|---|---|
| **SLT-01–07** (verified-field enforcement, tuned scrapers, detail-page enrichment groundwork, staleness check, scheduling, agent-prompt fixes, LICENSE/certifi/robots.txt) | **Closed, verified** | Original implementation commits; each has held up under every later live re-run without regressing, so not independently re-litigated here. |
| **SLT-08** (zero-row detection: a scraper finding fewer than `min_expected_docs` is a hard `error`, not a quiet success) | **Closed, verified** | Directly observed working as designed, repeatedly and recently: every SAMA scrape in this investigation correctly reported `ERROR ... zero_rows: selector or endpoint no longer matches` with a non-zero exit code, never a silent `ok`. |
| **SLT-09** (`last_modified`/footer timestamp kept structurally separate from `published_gregorian`/`published_hijri`; uid/`publication_key()` never derived from `last_modified`) | **Closed, verified** | Live-checked directly: 0/69 ZATCA rows have `published_gregorian == last_modified` (though note: `published_gregorian` is currently `None` for all 69 — the check is genuinely passing, not passing by coincidence of two populated values, but there's nothing populated to actively confuse yet either). More conclusively: simulated a footer-only change on 3 real stored rows through the actual `DocumentStore.upsert_many()` code path (not just `compute_uid()` in isolation) against a copied DB — `new_uids: []`, all 3 correctly landed in `updated_uids` instead, row count unchanged before/after. Confirmed done; no further action needed. |
| **SLT-10** (real snapshot fixtures + live smoke test) | **Closed, verified** | Established in earlier work; not independently re-verified in this final pass since nothing downstream has depended on or contradicted it. |
| **SLT-11** (dynamic verified-source listing) | **Closed, verified** | Established in earlier work; not independently re-verified in this final pass, same basis as SLT-10. |
| **SLT-02** (agent eval suite: citation validity, refusal correctness, hallucination rate vs. the 5% target) | **Closed, verified** | Citation validity 100% (20/20) on the final live run. Hallucination: raw pattern-matched rate looked like 30-50% depending on run, but that regex scorer can't distinguish a genuine fabrication from a disclosed live-check (explicitly permitted by `saudi-law-agent.md` when local data is insufficient). Added an `--judge` LLM-graded pass specifically for the hallucination suite with a rubric making that exact distinction; **two independent fresh full-suite runs both landed at 0.0% judged hallucination rate**, with a genuinely different raw-flagged trio of questions each time — strong evidence the correction is real, not a one-off. Every judge reclassification was individually checked against the actual answer text before being trusted, not accepted on the judge's say-so alone. |
| **SLT-02 — refusal scorer keyword-list precision gap** | **Partial, filed as its own low-priority item, non-blocking** | `contains_refusal()` missed two textbook-correct out-of-scope refusals (CMA, REGA) because their phrasing ("outside the sectors this project monitors", "not a source this project tracks") wasn't in its keyword list, and a real markdown-bold-formatting split in the actual answer text broke the first, wrong attempt at the fix. Now fixed for those two specific phrasings, confirmed against the real answer text. Does **not** cover a different pair of scorer misses (refusal-02/refusal-08) seen in an earlier run with yet other phrasing — this is a keyword list that will likely need occasional additions as new correct-but-differently-worded refusals surface; it is not, and probably can't be made, an exhaustive match. |
| **SLT-03** (live scrape working across all six configured sources) | **5 of 6 closed, verified; 1 of 6 a confirmed live limitation** | `bureau_of_experts`, `zatca_updates`, `citc`, `mhrsd_labor`, `umm_al_qura` all scraped live successfully with real, current row counts as of 2026-09-16. `sama_circulars` is a **confirmed live limitation, no fix available from this codebase**: SAMA's own site has every inner path (the Laws REST API included) returning a fake shell page instead of real content, confirmed via infrastructure-header analysis (a genuine SharePoint response carries distinctive headers the fake one lacks entirely — it never reaches SharePoint), not just by content inspection. First identified 2026-09-14; re-confirmed live 2026-09-16 and found to have *worsened* since (two more inner paths that worked two days earlier no longer do). This is a site-side outage or in-progress migration, not a selector bug — see `src/saudi_law_tracker/scrapers/sama.py`'s module docstring for the full investigation, and re-check periodically rather than re-diagnosing from scratch. SLT-08's zero-row detection is correctly reporting this as `ERROR` in the meantime, which is the correct behavior while it persists, not a bug to fix. |
| **A one-off DNS resolution incident, 2026-09-15T07:41 UTC** (all six sources logged `zero_rows`/`getaddrinfo failed` simultaneously) | **Closed, resolved, root cause identified** | Not a sixth-source problem or six independent site changes — the exact same OS-level DNS error hit six unrelated domains within ~107ms of each other, a signature only explainable by one shared, transient, local DNS-resolver hiccup on this machine at that moment. Confirmed non-recurring: two separate fresh scrapes since (2026-09-16) both resolve and fetch cleanly. No code change was needed or made; this was an infrastructure blip, not a defect. |
| **SLT-04** (Bureau of Experts detail-page enrichment: `reference_number` and `pdf_urls` population rate) | **`reference_number` closed, verified (94.4%); `pdf_urls` is a confirmed live limitation, not a bug (29.7%, expected to stay near there)** | Investigated whether the low `pdf_urls` rate was a selector miss or genuine data absence: live-sampled 20 currently-empty pages and found `Files/Download` present on **0 of 20** (vs. 2/2 positive-control pages, both correctly matched by the existing selector) — the selector works correctly, most Bureau of Experts law pages simply have no attached PDF. Confirmed by running `--backfill` across all 538 rows (463 re-fetched fresh): the percentage was **exactly unchanged** afterward. No further scraper change is expected to move this number; it reflects the source data, not a gap in this project. |

## Note on scope

Findings not listed above (anything from the original technical-reassessment
documents not named SLT-01 through SLT-11, or not surfaced in a later
targeted investigation) were not independently re-verified as part of this
pass — their last-known status stands as recorded in git history and prior
eval reports (`evals/agent/real_report_v*.json`), not re-asserted here.
