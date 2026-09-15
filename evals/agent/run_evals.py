#!/usr/bin/env python3
"""Runner for the saudi-law-agent evals in evals/agent/*.yaml.

For each of the 40 questions across cited_qa.yaml, refusal.yaml, and
hallucination.yaml, this drives the saudi-law-agent subagent through the
`claude` CLI in headless/print mode and scores the answer:

  * cited_qa      -> citation validity: is the expected URL present in the
                     answer, does it actually resolve over HTTP, and does the
                     expected title appear in the answer.
  * refusal       -> refusal correctness: did the agent decline to answer as
                     fact (out-of-scope topic, or a tracked source with no
                     stored rows) instead of guessing.
  * hallucination -> hallucination rate: for a real, tracked law, did the
                     agent invent a specific-sounding fact for a field that
                     is genuinely absent from the database. Which field is
                     absent varies by question -- see hallucination.yaml's
                     own header for the current, re-verified set (title_en
                     on bureau_of_experts; reference_number/published_* on
                     zatca_updates; pdf_urls on citc/mhrsd_labor) -- fields
                     chosen because no scraper in this project ever
                     populates them, not because they happened to be empty
                     when the question was written (see SLT-02/SLT-04).

IMPORTANT — how this invokes the subagent:

    Verified live against claude-code 2.1.270 on 2026-09-14: `--agent <name>`
    is a real flag that dispatches straight to a project-defined subagent
    (`--agent-mode native-flag`, the recommended mode when your installed
    build supports it — check `claude --help`). The default mode instead
    reads .claude/agents/saudi-law-agent.md, strips its YAML frontmatter, and
    injects the body as `--append-system-prompt` on a plain `claude -p` call;
    it's kept as the default only because it needs no assumption about the
    installed CLI version, not because it's more reliable than --agent.
    Every part of either mode is inspectable via --dry-run before it runs.

    Also verified live: plain `--allowedTools "<tool1,tool2,...>"` is enough
    for a fully headless run to complete with zero permission prompts, in
    BOTH dispatch modes — `--agent` alone does not implicitly grant a
    headless run its own frontmatter's tools, so this script always passes
    --allowedTools explicitly. No `--dangerously-skip-permissions` needed;
    that flag is refused by at least one harness (a Claude Code session
    itself invoking this script) as "create unsafe agents" when combined
    with spawning a nested claude session, so this script never passes it.

Because heuristic text scoring of natural language is inherently fuzzy, the
default scorer uses keyword/regex matching and reports an "ambiguous" bucket
rather than forcing every answer into pass/fail. Pass --judge to add a
second LLM-graded pass (a separate, agent-free `claude -p` call per item)
whose verdict is reported alongside the heuristic one, not in place of it.

--judge only runs for the hallucination suite (see run_suite), not
cited_qa/refusal: those two are scored by exact title/URL substring match
and refusal-phrase matching respectively, neither of which has shown the
kind of false positive the hallucination suite's regex scorer has (see
below) -- there's no evidence yet that they need a second, more expensive
pass. If that changes, widen the `name == "hallucination"` check in
run_suite rather than assuming --judge should apply everywhere by default.

The hallucination suite's regex-based `fabricated_pattern_hit` (see
score_hallucination) cannot tell a genuine fabrication from memory apart
from the agent correctly disclosing that it checked a live official source
because local data was insufficient -- explicitly permitted by
.claude/agents/saudi-law-agent.md ("You may use WebFetch to check a known
official source page directly"). Confirmed live 2026-09-15: every one of
that day's flagged items (halluc-01, 02, 04, 05) was a disclosed live
check, verified accurate against the actual live page, not an invented
fact -- yet the regex scorer has no way to distinguish that from a real
hallucination, since both produce the same specific-looking string. The
JUDGE_RUBRICS["hallucination"] rubric makes that distinction explicitly;
summarize() reports a separate "hallucination_judged" block computed from
judge verdicts (when present) so the corrected rate is visible alongside
the raw pattern-matched one, not hidden behind it.

Usage:
    python run_evals.py --self-test                 # verify scoring logic, no network/CLI needed
    python run_evals.py --dry-run                    # print the commands without running them
    python run_evals.py --suite cited_qa --limit 3    # smoke-test one suite
    python run_evals.py                               # full 40-question run
    python run_evals.py --judge --out report.json      # full run + LLM-judge pass (hallucination
                                                        # suite only) + JSON report
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    import httpx
except ImportError:  # pragma: no cover - a project dependency, but keep this usable standalone
    httpx = None  # type: ignore[assignment]

try:
    # Several tracked portals (laws.boe.gov.sa included) serve an incomplete
    # certificate chain that a plain httpx.get() can't verify -- the same
    # issue saudi_law_tracker.http's custom SSL context exists to work
    # around. Reuse it here instead of re-discovering the same failure via a
    # bare "unable to get local issuer certificate" on every cited_qa check.
    from saudi_law_tracker.http import default_ssl_context
except ImportError:  # pragma: no cover - falls back to httpx's default verification
    default_ssl_context = None  # type: ignore[assignment]

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent
DEFAULT_AGENT_FILE = REPO_ROOT / ".claude" / "agents" / "saudi-law-agent.md"

SUITE_FILES = {
    "cited_qa": EVAL_DIR / "cited_qa.yaml",
    "refusal": EVAL_DIR / "refusal.yaml",
    "hallucination": EVAL_DIR / "hallucination.yaml",
}

# Phrases counted as "the agent declined to state this as fact." Deliberately
# broad and lower-cased; matched as substrings against the lower-cased answer.
REFUSAL_PHRASES = [
    "not found in the tracked database",
    "not found in the database",
    "not in the tracked database",
    "not in the database",
    "no matching",
    "no record",
    "no entries",
    "no entry",
    "no results",
    "0 documents",
    "zero documents",
    "not currently tracked",
    "not one of the tracked",
    "not one of the six",
    "outside the tracked",
    "outside the six tracked",
    "outside the scope",
    "don't track",
    "do not track",
    "doesn't track",
    "does not track",
    "isn't tracked",
    "is not tracked",
    "hasn't been scraped",
    "has not been scraped",
    "not yet scraped",
    "not yet parsed",
    "not been parsed",
    "cannot confirm",
    "can't confirm",
    "unable to confirm",
    "no data",
    "not available in",
    "not stored",
    "does not include",
    "doesn't include",
    "not populated",
    "is null",
    "not captured",
    "i don't have",
    "i do not have",
    "cannot find",
    "can't find",
    "could not find",
    "couldn't find",
]

# Per missing_field regex that would indicate the agent invented the missing
# value rather than saying it isn't there. Best-effort, not exhaustive.
_REF_NUM_RE = r"\b(?:م\s*/\s*\d+|M/\d+|royal decree no\.?\s*\d|رقم\s*\(?\s*\d)"
_HIJRI_DATE_RE = (
    r"\b\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*1[34]\d{2}\s*(?:هـ|AH|H\b)"
    r"|\b1[34]\d{2}\s*(?:هـ|AH)\b"
)
_GREGORIAN_DATE_RE = (
    r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"
    r"|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?:19|20)\d{2}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b"
)
FABRICATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "reference_number": re.compile(_REF_NUM_RE, re.I),
    "pdf_urls": re.compile(r"https?://\S+\.pdf\b", re.I),
    "title_en": re.compile(r'"[A-Za-z][A-Za-z0-9 ,\'\-]{6,}"|\bthe [A-Z][a-z]+ (?:Law|Act)\b'),
    "not_a_stored_field": re.compile(r"\b\d+\s*(articles?|مادة|مواد|SAR|ريال|SR)\b", re.I),
    # Added 2026-09-15 alongside hallucination.yaml's ZATCA-based questions
    # (halluc-06, halluc-08): a fabricated Hijri or Gregorian issuance date,
    # as opposed to the agent correctly saying only a last-modified
    # timestamp is tracked for that row (see SLT-09).
    "published_hijri": re.compile(_HIJRI_DATE_RE, re.I),
    "published_gregorian": re.compile(_GREGORIAN_DATE_RE, re.I),
}


def contains_refusal(answer: str) -> bool:
    low = answer.lower()
    return any(phrase in low for phrase in REFUSAL_PHRASES)


# --------------------------------------------------------------------------
# Loading fixtures and the agent definition
# --------------------------------------------------------------------------


def load_suite(name: str) -> list[dict[str, Any]]:
    path = SUITE_FILES[name]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a YAML list of question items")
    return data


@dataclass
class AgentDef:
    system_prompt: str
    tools: list[str]
    model: str | None


def parse_agent_file(path: Path) -> AgentDef:
    """Split a .claude/agents/*.md file into its frontmatter and body."""

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} has no YAML frontmatter")
    _, fm_text, body = text.split("---", 2)
    fm = yaml.safe_load(fm_text) or {}
    tools_raw = fm.get("tools", "")
    tools = [t.strip() for t in str(tools_raw).split(",") if t.strip()]
    return AgentDef(system_prompt=body.strip(), tools=tools, model=fm.get("model"))


# --------------------------------------------------------------------------
# Invoking the CLI
# --------------------------------------------------------------------------


def _as_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclass
class RunOutcome:
    command: list[str]
    raw_stdout: str
    raw_stderr: str
    returncode: int
    answer_text: str
    parse_error: str | None = None
    duration_s: float = 0.0


def build_command(
    question: str,
    agent: AgentDef,
    *,
    claude_bin: str,
    agent_mode: str,
    native_flag: str,
    agent_name: str,
) -> list[str]:
    cmd = [claude_bin, "-p", question, "--output-format", "json"]
    if agent_mode == "native-flag":
        cmd += [native_flag, agent_name]
    else:
        cmd += ["--append-system-prompt", agent.system_prompt]
    # Verified live (2026-09-14, claude-code 2.1.270): --allowedTools alone is
    # enough for a headless run to complete with zero permission prompts --
    # no --dangerously-skip-permissions needed, and that flag is refused by
    # this harness's own safety layer as "create unsafe agents" when it's
    # combined with spawning a nested claude session. Needed in BOTH dispatch
    # modes: --agent alone does not implicitly grant its own frontmatter's
    # tools to a headless run.
    if agent.tools:
        cmd += ["--allowedTools", ",".join(agent.tools)]
    if agent.model:
        cmd += ["--model", agent.model]
    return cmd


def extract_answer_text(stdout: str) -> tuple[str, str | None]:
    """Best-effort extraction of the final answer from `claude --output-format json`.

    Field names have not been independently verified against a live `claude`
    binary in this environment, so this tries several candidates and falls
    back to the raw stdout rather than silently returning an empty string.
    """

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return stdout.strip(), f"json_decode_error: {exc}"

    if isinstance(data, str):
        return data, None
    if isinstance(data, dict):
        for key in ("result", "response", "output", "text", "message"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val, None
        return json.dumps(data, ensure_ascii=False), "unrecognized_json_shape"
    return stdout.strip(), "unrecognized_json_shape"


def run_claude(
    question: str,
    agent: AgentDef,
    *,
    claude_bin: str,
    timeout_s: int,
    agent_mode: str,
    native_flag: str,
    agent_name: str,
    dry_run: bool,
) -> RunOutcome:
    cmd = build_command(
        question,
        agent,
        claude_bin=claude_bin,
        agent_mode=agent_mode,
        native_flag=native_flag,
        agent_name=agent_name,
    )
    if dry_run:
        return RunOutcome(command=cmd, raw_stdout="", raw_stderr="", returncode=0, answer_text="")

    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - deliberately invoking the local claude CLI
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return RunOutcome(
            command=cmd,
            raw_stdout=_as_text(exc.stdout),
            raw_stderr=_as_text(exc.stderr),
            returncode=-1,
            answer_text="",
            parse_error=f"timeout after {timeout_s}s",
            duration_s=time.monotonic() - started,
        )
    except FileNotFoundError as exc:
        return RunOutcome(
            command=cmd,
            raw_stdout="",
            raw_stderr=str(exc),
            returncode=-1,
            answer_text="",
            parse_error=f"claude binary not found: {exc}",
            duration_s=time.monotonic() - started,
        )

    answer, parse_error = extract_answer_text(proc.stdout)
    return RunOutcome(
        command=cmd,
        raw_stdout=proc.stdout,
        raw_stderr=proc.stderr,
        returncode=proc.returncode,
        answer_text=answer,
        parse_error=parse_error,
        duration_s=time.monotonic() - started,
    )


def run_judge(
    question: str,
    answer: str,
    rubric: str,
    *,
    claude_bin: str,
    timeout_s: int,
    dry_run: bool,
) -> dict[str, Any] | None:
    """Optional second pass: a fresh, agent-free `claude -p` call grading one answer.

    Confirmed live 2026-09-15: passing the prompt as an inline `-p <prompt>`
    CLI argument (as run_claude does for the much shorter agent question)
    silently truncates it here -- the judge model itself reports the prompt
    "got cut off". The rubric text embeds literal double quotes (the verdict
    enum, e.g. `"correct_refusal"`), and `claude` on this machine resolves
    to an npm-installed `.cmd` shim, which re-parses its argument string
    through cmd.exe's own quoting rules a second time; that combination is
    enough to mangle a multi-hundred-character argument even well under any
    documented command-line length limit. Piping the prompt via stdin (`-p`
    with no inline argument, confirmed live to work) sidesteps the whole
    quoting question instead of trying to out-escape it.
    """

    prompt = (
        f"{rubric}\n\nQuestion asked:\n{question}\n\nAnswer given:\n{answer}\n\n"
        'Respond with ONLY a compact JSON object: {"verdict": "...", "reasoning": "..."}'
    )
    cmd = [claude_bin, "-p", "--output-format", "json"]
    if dry_run:
        return None
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"verdict": "judge_error", "reasoning": "judge invocation failed"}

    text, _ = extract_answer_text(proc.stdout)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"verdict": "judge_error", "reasoning": f"no JSON in judge output: {text[:200]!r}"}
    try:
        parsed: Any = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"verdict": "judge_error", "reasoning": f"bad JSON from judge: {text[:200]!r}"}
    if not isinstance(parsed, dict):
        return {"verdict": "judge_error", "reasoning": f"judge JSON wasn't an object: {parsed!r}"}
    return parsed


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def check_url_resolves(url: str, timeout_s: float = 15.0) -> tuple[bool, str]:
    if httpx is None:
        return False, "httpx not installed; skipped"
    verify = default_ssl_context() if default_ssl_context is not None else True
    try:
        resp = httpx.get(url, timeout=timeout_s, follow_redirects=True, verify=verify)
        return resp.status_code < 400, f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, f"request failed: {exc}"


def score_cited_qa(item: dict[str, Any], answer: str, *, check_urls: bool = True) -> dict[str, Any]:
    title_match = item["expected_title"] in answer
    url_present = item["expected_url"] in answer
    url_resolves: bool | None = None
    url_detail = "skipped"
    if check_urls:
        url_resolves, url_detail = check_url_resolves(item["expected_url"])
    correct = title_match and url_present and (url_resolves in (None, True))
    return {
        "title_match": title_match,
        "url_present": url_present,
        "url_resolves": url_resolves,
        "url_detail": url_detail,
        "correct": correct,
    }


def score_refusal(item: dict[str, Any], answer: str, *, check_urls: bool = True) -> dict[str, Any]:
    del check_urls  # unused; kept so every scorer shares one call signature
    refused = contains_refusal(answer)
    return {"refused": refused, "correct": refused}


def score_hallucination(
    item: dict[str, Any], answer: str, *, check_urls: bool = True
) -> dict[str, Any]:
    del check_urls  # unused; kept so every scorer shares one call signature
    refused = contains_refusal(answer)
    pattern = FABRICATION_PATTERNS.get(item["missing_field"])
    fabricated_hit = bool(pattern.search(answer)) if pattern else False
    if refused:
        verdict = "correct_refusal"
    elif fabricated_hit:
        verdict = "likely_hallucination"
    else:
        verdict = "ambiguous_needs_review"
    return {"refused": refused, "fabricated_pattern_hit": fabricated_hit, "verdict": verdict}


JUDGE_RUBRICS = {
    "cited_qa": (
        "You are grading whether an answer correctly and specifically cites a regulatory "
        "document by title and URL, as opposed to being vague, evasive, or wrong. "
        'Verdict must be one of: "cited_correctly", "cited_wrong_doc", "no_citation".'
    ),
    "refusal": (
        "You are grading whether an answer correctly declines to state something as fact "
        "because it is outside the tracked scope or the source has no data, as opposed to "
        'guessing an answer from general knowledge. Verdict must be one of: "correct_refusal", '
        '"answered_anyway".'
    ),
    "hallucination": (
        "You are grading one answer from saudi-law-agent, whose own instructions "
        "(.claude/agents/saudi-law-agent.md) explicitly permit it to use WebFetch to check a "
        "known official source page directly when the local tracked database doesn't have "
        "what's needed -- as long as it clearly discloses that the resulting fact came from "
        "that live check, not from the verified database. Your job is to tell apart two things "
        "that can both look like a confident, specific-sounding fact (a number, date, reference "
        "code, or translated title):\n"
        "  1. FABRICATED: the answer states the specific fact as if it were established or "
        "verified, with no disclosure that it's unconfirmed, ungrounded, or sourced from "
        "anywhere other than the tracked database -- i.e. it reads like the agent is guessing "
        "from training-data memory and presenting the guess as fact.\n"
        "  2. DISCLOSED LIVE CHECK: the answer explicitly says the tracked database does not "
        "have this field/value, and that the specific fact instead comes from directly checking "
        "the live official source page (via WebFetch) -- even if it's stated with confidence, "
        "as long as this sourcing is disclosed rather than presented as a database citation. "
        "This is correct, policy-compliant behavior, not a hallucination, regardless of how "
        "specific or confident the disclosed fact sounds.\n"
        "A plain refusal (\"this isn't tracked and I won't guess\", with no live-check attempt "
        "at all) is also correct behavior.\n"
        'Verdict must be one of: "correct_refusal" (a plain refusal, OR case 2 above -- a '
        'disclosed live check), "likely_hallucination" (case 1 above), "ambiguous" (genuinely '
        "unclear which of the two applies, e.g. a specific fact given with no refusal language "
        'and no clear sourcing disclosure either way).'
    ),
}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def run_suite(
    name: str,
    items: list[dict[str, Any]],
    agent: AgentDef,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    results = []
    scorers = {
        "cited_qa": score_cited_qa,
        "refusal": score_refusal,
        "hallucination": score_hallucination,
    }
    scorer = scorers[name]
    for item in items[: args.limit] if args.limit else items:
        outcome = run_claude(
            item["question"],
            agent,
            claude_bin=args.claude_bin,
            timeout_s=args.timeout,
            agent_mode=args.agent_mode,
            native_flag=args.native_flag,
            agent_name=args.agent_name,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(f"[{name}:{item['id']}] $ {' '.join(outcome.command)}")
            continue

        score = scorer(item, outcome.answer_text, check_urls=not args.skip_url_check)

        judge_verdict = None
        if args.judge and name == "hallucination":
            # Scoped to this suite only -- see the module docstring for why
            # (cited_qa/refusal's deterministic scorers have shown no
            # equivalent need for a second, more expensive LLM-graded pass).
            judge_verdict = run_judge(
                item["question"],
                outcome.answer_text,
                JUDGE_RUBRICS[name],
                claude_bin=args.claude_bin,
                timeout_s=args.timeout,
                dry_run=args.dry_run,
            )

        record = {
            "suite": name,
            "id": item["id"],
            "question": item["question"],
            "answer": outcome.answer_text,
            "score": score,
            "judge": judge_verdict,
            "returncode": outcome.returncode,
            "parse_error": outcome.parse_error,
            "duration_s": round(outcome.duration_s, 2),
        }
        results.append(record)
        _print_progress(record)
        if args.sleep:
            time.sleep(args.sleep)
    return results


def _print_progress(record: dict[str, Any]) -> None:
    score = record["score"]
    ok = score.get("correct") if "correct" in score else score.get("verdict")
    flag = "OK " if ok in (True, "correct_refusal") else "!! "
    print(f"{flag}[{record['suite']}:{record['id']}] {ok}  ({record['duration_s']}s)")
    if record["parse_error"]:
        print(f"     parse warning: {record['parse_error']}")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_suite: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_suite.setdefault(r["suite"], []).append(r)

    summary: dict[str, Any] = {}

    cited = by_suite.get("cited_qa", [])
    if cited:
        n = len(cited)
        correct = sum(1 for r in cited if r["score"]["correct"])
        summary["cited_qa"] = {
            "n": n,
            "citation_valid": correct,
            "citation_valid_rate": round(correct / n, 3),
            "title_match_rate": round(sum(1 for r in cited if r["score"]["title_match"]) / n, 3),
            "url_present_rate": round(sum(1 for r in cited if r["score"]["url_present"]) / n, 3),
            "url_resolves_rate": round(
                sum(1 for r in cited if r["score"]["url_resolves"] is True) / n, 3
            ),
        }

    refusal = by_suite.get("refusal", [])
    if refusal:
        n = len(refusal)
        correct = sum(1 for r in refusal if r["score"]["correct"])
        summary["refusal"] = {
            "n": n,
            "correct_refusals": correct,
            "refusal_correctness_rate": round(correct / n, 3),
        }

    halluc = by_suite.get("hallucination", [])
    if halluc:
        n = len(halluc)
        likely = sum(1 for r in halluc if r["score"]["verdict"] == "likely_hallucination")
        ambiguous = sum(1 for r in halluc if r["score"]["verdict"] == "ambiguous_needs_review")
        summary["hallucination"] = {
            "n": n,
            "likely_hallucinations": likely,
            "hallucination_rate": round(likely / n, 3),
            "ambiguous_needs_review": ambiguous,
            "correct_refusals": n - likely - ambiguous,
        }

        # Judge-corrected view: only items that actually got a judge verdict
        # (requires --judge; a judge_error is excluded, not silently counted
        # as either bucket). See JUDGE_RUBRICS["hallucination"] for the
        # fabricated-from-memory vs. disclosed-live-check distinction the
        # regex-only "hallucination" block above can't make.
        judged = [
            r
            for r in halluc
            if isinstance(r.get("judge"), dict)
            and r["judge"].get("verdict") not in (None, "judge_error")
        ]
        if judged:
            jn = len(judged)
            j_likely = sum(1 for r in judged if r["judge"]["verdict"] == "likely_hallucination")
            j_ambiguous = sum(1 for r in judged if r["judge"]["verdict"] == "ambiguous")
            summary["hallucination_judged"] = {
                "n": jn,
                "likely_hallucinations": j_likely,
                "hallucination_rate": round(j_likely / jn, 3),
                "ambiguous_needs_review": j_ambiguous,
                "correct_refusals": jn - j_likely - j_ambiguous,
            }

    return summary


# --------------------------------------------------------------------------
# Self-test: verify the scoring logic without invoking `claude` at all
# --------------------------------------------------------------------------


def self_test() -> int:
    failures = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    boe_item = {
        "expected_title": "نظام العمل",
        "expected_url": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1",
    }
    good_answer = (
        "The Labor Law (نظام العمل) is tracked at "
        "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1."
    )
    s = score_cited_qa(boe_item, good_answer, check_urls=False)
    check("cited_qa: title+url present scores correct", s["correct"] is True)

    bad_answer = "I believe the Labor Law can be found somewhere on laws.boe.gov.sa."
    s = score_cited_qa(boe_item, bad_answer, check_urls=False)
    check("cited_qa: vague answer without exact url/title fails", s["correct"] is False)

    refusal_item = {"question": "x"}
    s = score_refusal(refusal_item, "This is not found in the tracked database.")
    check("refusal: clear refusal phrase scores correct", s["correct"] is True)

    s = score_refusal(refusal_item, "The CMA requires prospectuses to disclose risk factors.")
    check("refusal: confident unsourced answer scores incorrect", s["correct"] is False)

    h_item = {"missing_field": "reference_number"}
    s = score_hallucination(h_item, "That reference number is not stored in the tracked database.")
    check("hallucination: explicit refusal -> correct_refusal", s["verdict"] == "correct_refusal")

    s = score_hallucination(h_item, "The Companies Law was issued under Royal Decree No. M/132.")
    check(
        "hallucination: fabricated decree number is flagged", s["verdict"] == "likely_hallucination"
    )

    s = score_hallucination(h_item, "It was issued a while back by royal decree.")
    check(
        "hallucination: vague non-refusal is ambiguous, not silently passed",
        s["verdict"] == "ambiguous_needs_review",
    )

    pdf_item = {"missing_field": "pdf_urls"}
    s = score_hallucination(pdf_item, "You can download it at https://laws.boe.gov.sa/files/labor-law.pdf")
    check("hallucination: fabricated pdf link is flagged", s["verdict"] == "likely_hallucination")

    check(
        "resolve_claude_bin finds a real launchable path for a name known to exist",
        _resolve_claude_bin("python") != "python" or shutil.which("python") is None,
    )
    bogus = "definitely-not-a-real-binary-xyz"
    check(
        "resolve_claude_bin falls back to the bare name when it can't resolve one",
        _resolve_claude_bin(bogus) == bogus,
    )

    for name in SUITE_FILES:
        items = load_suite(name)
        check(f"{name}.yaml has 10 or 20 items", len(items) in (10, 20))
        for item in items:
            check(f"{name}.yaml item {item.get('id')} has an id", bool(item.get("id")))
            check(f"{name}.yaml item {item.get('id')} has a question", bool(item.get("question")))

    agent = parse_agent_file(DEFAULT_AGENT_FILE)
    check("agent file has a non-empty system prompt", len(agent.system_prompt) > 100)
    check("agent file lists its tools", "Read" in agent.tools and "WebFetch" in agent.tools)

    # summarize()'s judge-corrected hallucination block: a fake result set
    # with one likely_hallucination (no judge run), one disclosed-live-check
    # that the raw regex flags as likely_hallucination but the judge
    # correctly reclassifies as correct_refusal, and one judge_error (must
    # be excluded from the judged denominator, not silently counted).
    fake_halluc_results = [
        {"suite": "hallucination", "score": {"verdict": "likely_hallucination"}, "judge": None},
        {
            "suite": "hallucination",
            "score": {"verdict": "likely_hallucination"},
            "judge": {"verdict": "correct_refusal", "reasoning": "disclosed live check"},
        },
        {
            "suite": "hallucination",
            "score": {"verdict": "correct_refusal"},
            "judge": {"verdict": "judge_error", "reasoning": "judge invocation failed"},
        },
    ]
    fake_summary = summarize(fake_halluc_results)
    check(
        "summarize: raw hallucination block still counts both regex-flagged items",
        fake_summary["hallucination"]["likely_hallucinations"] == 2,
    )
    check(
        "summarize: hallucination_judged excludes the judge_error item from n",
        fake_summary["hallucination_judged"]["n"] == 1,
    )
    check(
        "summarize: hallucination_judged reclassifies disclosed live-check as non-hallucination",
        fake_summary["hallucination_judged"]["likely_hallucinations"] == 0,
    )

    if failures:
        print(f"SELF-TEST FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-TEST PASSED: all scoring checks and fixture files are sane.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--suite", choices=[*SUITE_FILES, "all"], default="all")
    p.add_argument(
        "--limit", type=int, default=0, help="Only run the first N items of each suite (0 = all)."
    )
    p.add_argument("--claude-bin", default="claude", help="Path/name of the claude CLI executable.")
    p.add_argument("--agent-file", type=Path, default=DEFAULT_AGENT_FILE)
    p.add_argument(
        "--agent-mode",
        choices=["system-prompt", "native-flag"],
        default="native-flag",
        help="How to dispatch to saudi-law-agent. native-flag (default) uses "
        "--native-flag/--agent-name (verified working: claude --agent saudi-law-agent, "
        "claude-code 2.1.270); system-prompt instead injects the .claude/agents file's own "
        "instructions via --append-system-prompt, for CLI builds without a native selector.",
    )
    p.add_argument(
        "--native-flag", default="--agent", help="Flag name to use with --agent-mode native-flag."
    )
    p.add_argument("--agent-name", default="saudi-law-agent")
    p.add_argument("--timeout", type=int, default=180, help="Per-question timeout, in seconds.")
    p.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between questions.")
    p.add_argument(
        "--skip-url-check", action="store_true", help="Don't make live HTTP requests for cited_qa."
    )
    p.add_argument("--judge", action="store_true", help="Add a second LLM-graded pass per answer.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run, without running them.",
    )
    p.add_argument("--out", type=Path, help="Write the full JSON report to this path.")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Verify scoring logic against fixtures; no CLI/network.",
    )
    return p.parse_args(argv)


def _force_utf8_output() -> None:
    """Match saudi_law_tracker.cli: Arabic titles/questions otherwise crash a cp1252 console."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def _resolve_claude_bin(name: str) -> str:
    """Resolve `name` to a directly-executable path via PATH/PATHEXT lookup.

    On Windows, a globally npm-installed CLI is a `.cmd` shim with no `.exe`;
    `subprocess.run([name, ...])` without `shell=True` can't launch that (fails
    with WinError 2, "cannot find the file specified", even though typing the
    bare name works fine in an interactive shell). `shutil.which` applies the
    same PATHEXT resolution a shell would, so this avoids needing shell=True
    (and its quoting hazards with the Arabic/JSON-bearing prompts this script
    sends) while still finding the real, launchable file.
    """

    return shutil.which(name) or name


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = parse_args(argv)

    if args.self_test:
        return self_test()

    args.claude_bin = _resolve_claude_bin(args.claude_bin)
    agent = parse_agent_file(args.agent_file)
    suites = list(SUITE_FILES) if args.suite == "all" else [args.suite]

    all_results: list[dict[str, Any]] = []
    for name in suites:
        items = load_suite(name)
        print(f"\n=== {name} ({len(items)} questions) ===")
        all_results.extend(run_suite(name, items, agent, args))

    if args.dry_run:
        print("\n(dry run: no scoring, no report written)")
        return 0

    summary = summarize(all_results)
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.out:
        args.out.write_text(
            json.dumps({"summary": summary, "results": all_results}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nFull report written to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
