# saudi-law-agent evals

40 questions across three YAML fixtures, scored by `run_evals.py`:

| file                   | n  | tests                                                              |
|------------------------|----|---------------------------------------------------------------------|
| `cited_qa.yaml`        | 20 | citation validity — real, verified `bureau_of_experts` rows the agent must cite by exact title + URL |
| `refusal.yaml`         | 10 | refusal correctness — out-of-scope topics, and tracked-but-empty sources (`sama_circulars`, `citc`) |
| `hallucination.yaml`   | 10 | hallucination rate — real tracked laws, asked about fields (`reference_number`, `pdf_urls`, `title_en`) that are genuinely null for every row |

## Before you run it

`cited_qa.yaml` was built from a live dump of `data/regulations.db` — see
each file's header comment. If the database has been re-scraped or the
`bureau_of_experts` scraper's selectors changed since, re-check the expected
titles/URLs still match before trusting a run's results:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/regulations.db')
for r in conn.execute(\"SELECT title, url, verified FROM regulations WHERE source_key='bureau_of_experts'\"):
    print(r)
"
```

Also note: this repo's database predates the `verified` column, so on a
fresh checkout every `bureau_of_experts` row still reads `verified=0` until
either (a) the scraper re-runs and re-inserts them, or (b) you backfill
directly (`UPDATE regulations SET verified = 1 WHERE source_key =
'bureau_of_experts'` — safe, since that scraper is the tuned one and its
rows are exactly what `verified=true` is supposed to mean).

## Running

```bash
# 1. Verify the scoring logic itself, no claude CLI or network needed:
python evals/agent/run_evals.py --self-test

# 2. See exactly what would be sent to `claude`, without spending anything:
python evals/agent/run_evals.py --dry-run

# 3. Smoke-test one suite, a couple of items:
python evals/agent/run_evals.py --suite cited_qa --limit 3

# 4. Full 40-question run with a JSON report:
python evals/agent/run_evals.py --out report.json
```

## How it dispatches to the subagent

There's no flag for "run headless, dispatch straight to subagent X" that
this repo could independently verify against a live `claude` binary. Default
mode (`--agent-mode system-prompt`) sidesteps that by reading
`.claude/agents/saudi-law-agent.md` itself, stripping its frontmatter, and
passing the body as `--append-system-prompt` on a plain `claude -p` call,
with `--allowedTools` restricted to the tools that file's frontmatter lists.
Every part of this is visible via `--dry-run` before it spends anything.

If your installed `claude` build has a real native subagent-selector flag,
pass `--agent-mode native-flag` (and `--native-flag`/`--agent-name` if it's
not literally `--agent saudi-law-agent`) to use that instead.

## Scoring caveats

Scoring is heuristic (substring/regex matching on the answer text), plus a
live HTTP check that each cited URL actually resolves. It is a first-pass
signal, not ground truth — skim the `--out` JSON report's `answer` fields
for anything scored `ambiguous_needs_review` (hallucination.yaml) or marked
incorrect, before trusting a rate number on its own. Pass `--judge` to add a
second, independent LLM-graded verdict per answer alongside the heuristic
one (extra `claude` calls, so extra cost/time).
