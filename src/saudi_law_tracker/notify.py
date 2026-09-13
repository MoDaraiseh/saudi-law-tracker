"""Optional outbound notification for newly discovered documents."""

from __future__ import annotations

import httpx

from .logging import get_logger
from .models import RegulatoryDocument

log = get_logger(__name__)


async def notify_new_documents(
    webhook_url: str | None,
    source_name: str,
    docs: list[RegulatoryDocument],
    updated: list[RegulatoryDocument] | None = None,
) -> None:
    updated = updated or []
    if not webhook_url or not (docs or updated):
        return

    counts = []
    if docs:
        counts.append(f"{len(docs)} new")
    if updated:
        counts.append(f"{len(updated)} changed")
    lines = [f"*{source_name}* — {', '.join(counts)}:"]
    for d in docs[:20]:
        lines.append(f"• <{d.url}|{d.title}>  ({d.display_date})")
    for d in updated[:20]:
        lines.append(f"• _changed_ <{d.url}|{d.title}>  ({d.display_date})")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(webhook_url, json={"text": "\n".join(lines)})
    except httpx.HTTPError as exc:  # notification failure must not break a run
        log.warning("notify.failed", error=str(exc))
