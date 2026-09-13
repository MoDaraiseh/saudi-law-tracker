"""Orchestration: run one or many source scrapers, persist, diff, notify."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from .config import SourceConfig, get_settings, load_sources
from .http import HttpClient
from .logging import get_logger
from .models import ScrapeResult
from .notify import notify_new_documents
from .scrapers import get_scraper, load_all_scrapers
from .storage import DocumentStore, RunState

log = get_logger(__name__)


async def run_source(source: SourceConfig, *, dry_run: bool = False) -> ScrapeResult:
    settings = get_settings()
    store = DocumentStore(settings)
    started = datetime.now(UTC)
    errors: list[str] = []
    documents = []

    async with HttpClient(
        user_agent=settings.http_user_agent,
        timeout=source.timeout,
        max_retries=source.max_retries,
        request_delay=source.request_delay,
    ) as http:
        scraper = get_scraper(source.scraper)(source, http, store)
        try:
            async for doc in scraper.discover():
                documents.append(doc)
        except Exception as exc:  # noqa: BLE001 - one bad source shouldn't kill the batch
            errors.append(f"{type(exc).__name__}: {exc}")
            log.exception("source.failed", source=source.key)

    new_uids: list[str] = []
    updated_uids: list[str] = []
    if documents and not dry_run:
        new_uids, updated_uids = store.upsert_many(source.key, documents)
        new_set, updated_set = set(new_uids), set(updated_uids)
        new_docs = [d for d in documents if d.uid in new_set]
        updated_docs = [d for d in documents if d.uid in updated_set]
        await notify_new_documents(
            settings.notify_webhook_url, source.name, new_docs, updated_docs
        )

    result = ScrapeResult(
        source_key=source.key,
        started_at=started,
        finished_at=datetime.now(UTC),
        documents=documents,
        new_uids=new_uids,
        updated_uids=updated_uids,
        errors=errors,
    )
    if not dry_run:
        detail = "; ".join(errors) if errors else f"{len(documents)} docs"
        RunState(settings).mark(source.key, ok=result.ok, detail=detail)
    log.info(
        "source.done",
        source=source.key,
        found=len(documents),
        new=len(new_uids),
        updated=len(updated_uids),
        ok=result.ok,
    )
    return result


async def run_all(
    keys: list[str] | None = None, *, dry_run: bool = False
) -> list[ScrapeResult]:
    load_all_scrapers()
    settings = get_settings()
    sources = [s for s in load_sources() if s.enabled and (keys is None or s.key in keys)]
    if not sources:
        log.warning("no.matching.sources", requested=keys)
        return []

    sem = asyncio.Semaphore(settings.max_concurrency)

    async def _guarded(src: SourceConfig) -> ScrapeResult:
        async with sem:
            return await run_source(src, dry_run=dry_run)

    return await asyncio.gather(*(_guarded(s) for s in sources))
