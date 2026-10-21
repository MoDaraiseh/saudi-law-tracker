"""Command-line interface."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import UTC, date, datetime, timedelta

import typer

from .config import get_settings, load_sources
from .logging import configure_logging
from .models import RegulatoryDocument, ScrapeResult
from .pipeline import run_all
from .scrapers import get_scraper, load_all_scrapers, registered_keys
from .storage import DocumentStore, RunState

app = typer.Typer(add_completion=False, help="Track Saudi regulatory publications.")


def _force_utf8_output() -> None:
    """Make stdout/stderr UTF-8 so Arabic text and dashes don't crash a cp1252 console."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def _main() -> None:
    _force_utf8_output()
    configure_logging(get_settings().log_level)


@app.command("sources")
def list_sources() -> None:
    """List configured sources, whether a scraper is registered for each, and
    whether that scraper is tuned (emits verified=True rows) or still on the
    generic listing harvester."""

    load_all_scrapers()
    known = set(registered_keys())
    for s in load_sources():
        flag = "on " if s.enabled else "off"
        if s.scraper not in known:
            wired = "MISSING scraper"
        else:
            wired = "tuned  " if get_scraper(s.scraper).tuned else "untuned"
        typer.echo(f"[{flag}] {s.key:20s} {wired:16s} {s.name}")


def _new_entry_lines(results: list[ScrapeResult]) -> list[str]:
    """One block per newly stored document, newest publication first."""

    new: list[tuple[str, RegulatoryDocument]] = []
    for r in results:
        new_uids = set(r.new_uids)
        new.extend((r.source_key, doc) for doc in r.documents if doc.uid in new_uids)
    new.sort(key=lambda pair: pair[1].publication_key(), reverse=True)

    if not new:
        return ["No new entries."]
    lines = [f"New entries ({len(new)}):"]
    for source_key, doc in new:
        lines.append(f"  [{source_key}] {doc.title}  ({doc.display_date})")
        lines.append(f"      {doc.url}")
    return lines


@app.command("scrape")
def scrape(
    source: list[str] = typer.Option(None, "--source", "-s", help="Source key; repeatable."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and parse, but don't persist."),
    backfill: bool = typer.Option(
        False,
        "--backfill",
        help="Walk a source's full result set once instead of its normal bounded window, "
        "to retroactively fill in older rows (e.g. bureau_of_experts's reference_number "
        "and pdf_urls). Slower and heavier than a normal run; other scrapers ignore it.",
    ),
) -> None:
    """Run scrapers for all enabled sources, or just the ones named."""

    results = asyncio.run(run_all(source or None, dry_run=dry_run, backfill=backfill))
    for r in results:
        status = "OK" if r.ok else "ERROR"
        typer.echo(
            f"{status:5s} {r.source_key:20s} found={len(r.documents):4d} "
            f"new={len(r.new_uids):3d} updated={len(r.updated_uids):3d}"
        )
        for err in r.errors:
            typer.echo(f"      ! {err}")

    typer.echo("")
    for line in _new_entry_lines(results):
        typer.echo(line)
    raise typer.Exit(0 if all(r.ok for r in results) else 1)


def _is_stale(last_run: str, max_age_hours: float, *, now: datetime) -> bool:
    """True if `last_run` (an isoformat timestamp, or "never") is missing or
    older than `max_age_hours`."""

    if last_run == "never":
        return True
    try:
        run_at = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=UTC)
    return now - run_at > timedelta(hours=max_age_hours)


@app.command("status")
def status(
    max_age_hours: float | None = typer.Option(
        None,
        "--max-age-hours",
        help="Also flag any enabled source whose last successful run is older than "
        "this many hours (or that has never run) as STALE, and exit non-zero if any "
        "are found. Meant for a scheduled run to alert on -- see README's Scheduling "
        "section.",
    ),
) -> None:
    """Show last-run status and stored document counts per source."""

    settings = get_settings()
    runs = RunState(settings)
    store = DocumentStore(settings)
    now = datetime.now(UTC)
    any_stale = False

    for s in load_sources():
        info = runs.get(s.key)
        count = store.count(s.key)
        last_run = info.get("last_run", "never")
        # Staleness is judged on the last *successful* run, as documented: a
        # source that runs daily but fails every time must still be flagged.
        last_ok = RunState.describe_last_success(info)
        line = (
            f"{s.key:20s} docs={count:5d} last_run={last_run:32s} {info.get('status', '-'):5s}"
            f" last_ok={last_ok}"
        )

        if max_age_hours is not None and s.enabled and _is_stale(last_ok, max_age_hours, now=now):
            any_stale = True
            line += "  STALE"

        typer.echo(line)

    if max_age_hours is not None and any_stale:
        raise typer.Exit(1)


@app.command("export")
def export(
    source: str = typer.Argument(..., help="Source key to export."),
    limit: int = typer.Option(20, "--limit", "-n", min=1),
) -> None:
    """Print the most recently published stored documents as JSON."""

    docs = list(DocumentStore(get_settings()).load(source).values())
    docs.sort(key=lambda d: d.published_gregorian or d.first_seen.date(), reverse=True)
    payload = [json.loads(d.model_dump_json()) for d in docs[:limit]]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"expected YYYY-MM-DD, got {value!r}") from exc


@app.command("query")
def query(
    source: list[str] = typer.Option(None, "--source", "-s", help="Source key (repeatable)."),
    doc_type: list[str] = typer.Option(None, "--type", "-t", help="doc_type (repeatable)."),
    sector: str = typer.Option(
        None, "--sector", help="Substring of source key or category, e.g. 'labor', 'tax'."
    ),
    text: str = typer.Option(None, "--text", "-q", help="Substring of title or summary."),
    since: str = typer.Option(None, "--since", help="Published on/after (YYYY-MM-DD)."),
    until: str = typer.Option(None, "--until", help="Published on/before (YYYY-MM-DD)."),
    include_unverified: bool = typer.Option(
        False,
        "--include-unverified",
        help="Also include rows from untuned scrapers (verified=false). "
        "By default only verified rows are returned.",
    ),
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Max rows."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Search stored regulations across all sources (no raw SQL needed).

    Only verified rows are returned by default — pass --include-unverified to
    also see rows from untuned scrapers, which should not be cited as fact.
    """

    docs = DocumentStore(get_settings()).query(
        sources=source or None,
        doc_types=doc_type or None,
        sector=sector,
        text=text,
        since=_parse_date(since),
        until=_parse_date(until),
        verified=None if include_unverified else True,
        limit=limit,
    )

    if as_json:
        payload = [json.loads(d.model_dump_json()) for d in docs]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not docs:
        typer.echo("No matching regulations.")
        return
    for d in docs:
        flag = "" if d.verified else "  [UNVERIFIED]"
        typer.echo(f"{d.display_date:>15}  [{d.source_key}] {d.doc_type}{flag}")
        typer.echo(f"      {d.title}")
        typer.echo(f"      {d.url}")
    typer.echo(f"\n{len(docs)} result(s).")


if __name__ == "__main__":
    app()
