from __future__ import annotations

import pytest

from saudi_law_tracker.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv("SLT_DATA_DIR", raising=False)
    s = Settings(data_dir=tmp_path / "data")
    s.ensure_dirs()
    return s
