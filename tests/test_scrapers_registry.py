from __future__ import annotations

from saudi_law_tracker.config import load_sources
from saudi_law_tracker.scrapers import load_all_scrapers, registered_keys


def test_every_enabled_source_has_a_registered_scraper():
    load_all_scrapers()
    known = set(registered_keys())
    missing = [s.key for s in load_sources() if s.enabled and s.scraper not in known]
    assert not missing, f"sources without a scraper: {missing}"


def test_source_keys_are_unique():
    keys = [s.key for s in load_sources()]
    assert len(keys) == len(set(keys))
