from __future__ import annotations

from saudi_law_tracker.config import load_sources
from saudi_law_tracker.scrapers import get_scraper, load_all_scrapers, registered_keys


def test_every_enabled_source_has_a_registered_scraper():
    load_all_scrapers()
    known = set(registered_keys())
    missing = [s.key for s in load_sources() if s.enabled and s.scraper not in known]
    assert not missing, f"sources without a scraper: {missing}"


def test_source_keys_are_unique():
    keys = [s.key for s in load_sources()]
    assert len(keys) == len(set(keys))


def test_tuned_scrapers_actually_emit_verified_true():
    """`BaseScraper.tuned` is a plain class attribute nothing enforces against
    the scraper's actual `discover()` body (see base.py's docstring) -- this
    at least catches the class forgetting to flip it after being written to
    set `verified=True`, or a stale `tuned = True` left on a scraper that no
    longer does (by grepping its source, not by scraping it live -- that's
    test_live_smoke.py's job)."""

    import inspect

    load_all_scrapers()
    for key in registered_keys():
        cls = get_scraper(key)
        if cls.tuned:
            source = inspect.getsource(cls)
            assert "verified=True" in source, (
                f"{key}: BaseScraper.tuned is True but its class body has no "
                "verified=True -- `saudi-law-tracker sources` would be lying"
            )
