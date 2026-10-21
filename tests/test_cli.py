from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from saudi_law_tracker.cli import _is_stale, _new_entry_lines
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


def test_is_stale_true_when_never_run():
    assert _is_stale("never", 36, now=_NOW) is True


def test_is_stale_false_within_threshold():
    recent = (_NOW - timedelta(hours=1)).isoformat()
    assert _is_stale(recent, 36, now=_NOW) is False


def test_is_stale_true_past_threshold():
    old = (_NOW - timedelta(hours=37)).isoformat()
    assert _is_stale(old, 36, now=_NOW) is True


def test_is_stale_treats_naive_timestamp_as_utc():
    naive = (_NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert _is_stale(naive, 36, now=_NOW) is False


def test_is_stale_true_for_unparseable_timestamp():
    assert _is_stale("not-a-timestamp", 36, now=_NOW) is True


def test_is_stale_boundary_is_exclusive():
    exactly_at_threshold = (_NOW - timedelta(hours=36)).isoformat()
    assert _is_stale(exactly_at_threshold, 36, now=_NOW) is False
    just_past = (_NOW - timedelta(hours=36, seconds=1)).isoformat()
    assert _is_stale(just_past, 36, now=_NOW) is True


def _status(settings, monkeypatch, *args: str):
    from typer.testing import CliRunner

    from saudi_law_tracker import cli
    from saudi_law_tracker.config import SourceConfig

    sources = [
        SourceConfig(key=k, name=k, scraper="x", base_url="https://example.gov.sa")
        for k in ("healthy", "failing", "never_ok")
    ]
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "load_sources", lambda: sources)
    return CliRunner().invoke(cli.app, ["status", *args])


def test_status_flags_source_that_runs_but_keeps_failing(settings, monkeypatch):
    from saudi_law_tracker.storage import RunState

    runs = RunState(settings)
    runs.mark("healthy", ok=True)
    runs.mark("failing", ok=True)
    runs.mark("failing", ok=False, detail="zero_rows")  # ran just now, but failed
    runs.mark("never_ok", ok=False, detail="zero_rows")

    # Pretend the "failing" source's last success was 3 days ago.
    import json

    data = json.loads(runs.path.read_text(encoding="utf-8"))
    data["failing"]["last_success"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    runs.path.write_text(json.dumps(data), encoding="utf-8")

    result = _status(settings, monkeypatch, "--max-age-hours", "36")
    lines = {line.split()[0]: line for line in result.output.splitlines() if line.strip()}

    assert result.exit_code == 1
    assert "STALE" not in lines["healthy"]
    assert "STALE" in lines["failing"]
    assert "STALE" in lines["never_ok"] and "last_ok=never" in lines["never_ok"]


def test_status_all_recently_successful_exits_zero(settings, monkeypatch):
    from saudi_law_tracker.storage import RunState

    runs = RunState(settings)
    for key in ("healthy", "failing", "never_ok"):
        runs.mark(key, ok=True)

    result = _status(settings, monkeypatch, "--max-age-hours", "36")

    assert result.exit_code == 0, result.output
    assert "STALE" not in result.output


def test_settings_reads_project_env_file_from_any_directory():
    from saudi_law_tracker.config import PROJECT_ROOT, Settings

    env_files = Settings.model_config["env_file"]
    assert isinstance(env_files, tuple)
    assert env_files[0] == PROJECT_ROOT / ".env"


def test_relative_data_dir_is_anchored_to_project_root(monkeypatch):
    from pathlib import Path

    from saudi_law_tracker.config import PROJECT_ROOT, Settings

    monkeypatch.setenv("SLT_DATA_DIR", "./data")
    assert Settings().data_dir == PROJECT_ROOT / "data"
    absolute = Path(PROJECT_ROOT.anchor) / "elsewhere" / "data"
    assert Settings(data_dir=absolute).data_dir == absolute
