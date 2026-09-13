from __future__ import annotations

from datetime import UTC, date, datetime

from saudi_law_tracker.cli import _new_entry_lines
from saudi_law_tracker.models import DocumentType, RegulatoryDocument, ScrapeResult

_NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _doc(url: str, title: str, published: date) -> RegulatoryDocument:
    return RegulatoryDocument(
        source_key="demo",
        title=title,
        doc_type=DocumentType.LAW,
        url=url,
        published_gregorian=published,
    )


def _result(*docs: RegulatoryDocument) -> ScrapeResult:
    return ScrapeResult(
        source_key="demo",
        started_at=_NOW,
        finished_at=_NOW,
        documents=list(docs),
        new_uids=[d.uid for d in docs],
    )


def test_new_entry_lines_lists_new_docs_newest_first():
    older = _doc("https://e.gov.sa/1", "Older law", date(2024, 1, 1))
    newer = _doc("https://e.gov.sa/2", "Newer law", date(2024, 9, 1))

    lines = _new_entry_lines([_result(older, newer)])

    assert lines[0] == "New entries (2):"
    assert "[demo] Newer law  (2024-09-01)" in lines[1]
    assert lines[2] == "      https://e.gov.sa/2"
    assert "Older law" in lines[3]


def test_new_entry_lines_ignores_non_new_documents():
    d = _doc("https://e.gov.sa/1", "A law", date(2024, 1, 1))
    result = ScrapeResult(
        source_key="demo",
        started_at=_NOW,
        finished_at=_NOW,
        documents=[d],
        new_uids=[],
    )
    assert _new_entry_lines([result]) == ["No new entries."]
