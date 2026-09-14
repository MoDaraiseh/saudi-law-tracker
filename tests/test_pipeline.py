from __future__ import annotations

from saudi_law_tracker import pipeline
from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import RegulatoryDocument
from saudi_law_tracker.scrapers.base import BaseScraper, register
from saudi_law_tracker.storage import RunState

# Module-scoped mutable knob: how many documents the fake scraper below
# yields on its next discover() call. Set it at the top of each test.
_DOC_COUNT = {"n": 0}


@register("test_zero_rows_scraper")
class _CountControlledScraper(BaseScraper):
    """Never touches self.http -- yields exactly _DOC_COUNT['n'] fake docs."""

    async def discover(self):
        for i in range(_DOC_COUNT["n"]):
            yield RegulatoryDocument(
                source_key=self.source.key,
                title=f"Test doc {i}",
                url=f"https://example.gov.sa/{i}",
                verified=True,
            )


def _source(min_expected_docs: int = 1) -> SourceConfig:
    return SourceConfig(
        key="test_source",
        name="Test Source",
        scraper="test_zero_rows_scraper",
        base_url="https://example.gov.sa",
        min_expected_docs=min_expected_docs,
    )


async def test_run_source_flags_zero_rows_as_error(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 0

    result = await pipeline.run_source(_source(min_expected_docs=1))

    assert result.ok is False
    assert "zero_rows: selector or endpoint no longer matches" in result.errors
    info = RunState(settings).get("test_source")
    assert info["status"] == "error"
    assert "zero_rows" in info["detail"]


async def test_run_source_below_threshold_is_error_even_with_some_docs(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 2  # found some, but fewer than min_expected_docs

    result = await pipeline.run_source(_source(min_expected_docs=5))

    assert result.ok is False
    assert any("zero_rows" in e for e in result.errors)


async def test_run_source_meeting_threshold_is_ok(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 3

    result = await pipeline.run_source(_source(min_expected_docs=1))

    assert result.ok is True
    assert result.errors == []
    info = RunState(settings).get("test_source")
    assert info["status"] == "ok"


async def test_run_source_zero_rows_check_applies_even_in_dry_run(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 0

    result = await pipeline.run_source(_source(min_expected_docs=1), dry_run=True)

    assert result.ok is False
    assert "zero_rows: selector or endpoint no longer matches" in result.errors


async def test_run_source_min_expected_docs_zero_opts_out(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 0

    result = await pipeline.run_source(_source(min_expected_docs=0))

    assert result.ok is True
    assert result.errors == []
