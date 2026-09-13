"""Command-line interface."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import date

import typer

from .config import get_settings, load_sources
from .logging import configure_logging
from .models import ScrapeResult
from .pipeline import run_all
from .scrapers import load_all_scrapers, registered_keys
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
    """List configured sources and whether a scraper is registered for each."""

    load_all_scrapers()
    known = set(registered_keys())
    for s in load_sources():
        flag = "on " if s.enabled else "off"
        wired = "ok" if s.scraper in known else "MISSING scraper"
        typer.echo(f"[{flag}] {s.key:20s} {wired:16s} {s.name}")


def _new_entry_lines(results: list[ScrapeResult]) -> list[str]:
    """One block per newly stored document, newest publication first."""

    new = [
        (r.source_key, doc)
        for r in results
        for doc in r.documents
        if doc.uid in set(r.new_uids)
    ]
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
) -> None:
    """Run scrapers for all enabled sources, or just the ones named."""

    results = asyncio.run(run_all(source or None, dry_run=dry_run))
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


@app.command("status")
def status() -> None:
    """Show last-run status and stored document counts per source."""

    settings = get_settings()
    runs = RunState(settings)
    store = DocumentStore(settings)
    for s in load_sources():
        info = runs.get(s.key)
        count = store.count(s.key)
        typer.echo(
            f"{s.key:20s} docs={count:5d} "
            f"last_run={info.get('last_run', 'never'):32s} {info.get('status', '-')}"
        )


@app.command("export")
def export(
    source: str = typer.Argument(..., help="Source key to export."),
    limit: int = typer.Option(20, "--limit", "-n"),
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
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Search stored regulations across all sources (no raw SQL needed)."""

    docs = DocumentStore(get_settings()).query(
        sources=source or None,
        doc_types=doc_type or None,
        sector=sector,
        text=text,
        since=_parse_date(since),
        until=_parse_date(until),
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
        typer.echo(f"{d.display_date:>15}  [{d.source_key}] {d.doc_type}")
        typer.echo(f"      {d.title}")
        typer.echo(f"      {d.url}")
    typer.echo(f"\n{len(docs)} result(s).")


if __name__ == "__main__":
    app()
