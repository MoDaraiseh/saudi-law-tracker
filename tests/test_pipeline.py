from __future__ import annotations

from saudi_law_tracker import pipeline
from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import RegulatoryDocument
from saudi_law_tracker.scrapers.base import BaseScraper, register
from saudi_law_tracker.storage import DocumentStore, RunState

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


@register("test_duplicate_scraper")
class _DuplicateScraper(BaseScraper):
    """Yields the same document twice, as a listing that repeats a row would."""

    async def discover(self):
        for _ in range(2):
            yield RegulatoryDocument(
                source_key=self.source.key,
                title="Repeated doc",
                url="https://example.gov.sa/dup",
                verified=True,
            )


async def test_run_source_tolerates_duplicate_documents(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    source = _source(min_expected_docs=1).model_copy(update={"scraper": "test_duplicate_scraper"})

    result = await pipeline.run_source(source)

    assert result.ok is True, result.errors
    assert len(result.documents) == 1
    assert len(result.new_uids) == 1


async def test_run_source_storage_failure_is_a_source_error_not_a_crash(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    _DOC_COUNT["n"] = 2

    def boom(self, source_key, docs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(DocumentStore, "upsert_many", boom)
    result = await pipeline.run_source(_source(min_expected_docs=1))

    assert result.ok is False
    assert any("storage: RuntimeError: disk full" in e for e in result.errors)
    assert RunState(settings).get("test_source")["status"] == "error"


def test_run_state_keeps_last_success_across_failures(settings):
    runs = RunState(settings)
    runs.mark("s", ok=True)
    ok_at = runs.get("s")["last_success"]
    runs.mark("s", ok=False, detail="zero_rows")
    info = runs.get("s")
    assert info["status"] == "error"
    assert info["last_success"] == ok_at
    assert info["last_run"] >= ok_at


def test_run_state_never_succeeded_says_never(settings):
    runs = RunState(settings)
    runs.mark("s", ok=False)
    runs.mark("s", ok=False)
    assert runs.get("s")["last_success"] == "never"
    assert RunState.last_success(runs.get("s")) is None
    assert RunState.describe_last_success(runs.get("s")) == "never"
    assert RunState.describe_last_success({}) == "never"


def test_run_state_legacy_entries_without_last_success(settings):
    legacy_ok = {"last_run": "2026-09-01T00:00:00+00:00", "status": "ok"}
    legacy_err = {"last_run": "2026-09-01T00:00:00+00:00", "status": "error"}
    assert RunState.last_success(legacy_ok) == "2026-09-01T00:00:00+00:00"
    assert RunState.last_success(legacy_err) is None
    # An old failing entry doesn't say whether any earlier run succeeded.
    assert RunState.describe_last_success(legacy_err) == "unknown"

    # Re-marking it as failed again must not turn "unknown" into "never".
    import json

    runs = RunState(settings)
    runs.path.write_text(json.dumps({"s": legacy_err}), encoding="utf-8")
    runs.mark("s", ok=False)
    assert RunState.describe_last_success(runs.get("s")) == "unknown"
    runs.mark("s", ok=True)
    assert RunState.describe_last_success(runs.get("s")) == runs.get("s")["last_run"]
