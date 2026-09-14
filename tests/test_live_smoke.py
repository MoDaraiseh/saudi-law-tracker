"""Live smoke test: hits every enabled source's real site and asserts each
one still returns at least one verified, dated row.

This is the guard that should have caught SLT-03 originally: a unit test
against a hand-written fixture keeps passing forever even after the real
site's markup moves out from under the scraper's selectors, because the
fixture never changes. Only a real request against the live page can catch
that -- which is also exactly why this is *not* part of the normal test
run. It's excluded by default (`-m "not live"` in pyproject.toml's
`addopts`) since it's slow, makes real network requests, and its outcome
depends on sites this project doesn't control. Run it explicitly:

    pytest -m live tests/test_live_smoke.py

`scrape.cmd` (the scheduled job) runs it after the normal scrape, so a
selector drift shows up as a named, per-source test failure in the log --
not just a `zero_rows` line buried in `scrape`'s own output. The two checks
are deliberately redundant: `min_expected_docs`/`zero_rows` in pipeline.py
is what actually blocks a bad run's data from looking like a quiet success,
while this test is what a human (or an alert on the scheduled job) notices
first.

A source can fail this test for two different reasons, and the failure
message doesn't try to guess which: the scraper's selectors have drifted
(a real bug, fix the scraper), or the live site itself is down or has
changed its content entirely (not a scraper bug -- see sama.py's docstring
for a source that is *currently* failing this test for exactly that reason,
confirmed live and left that way deliberately rather than silenced).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from saudi_law_tracker.config import SourceConfig, load_sources
from saudi_law_tracker.http import HttpClient
from saudi_law_tracker.models import RegulatoryDocument
from saudi_law_tracker.scrapers import get_scraper, load_all_scrapers

pytestmark = pytest.mark.live

load_all_scrapers()


class _DiscardingStore:
    """A couple of scrapers (bureau_of_experts) call store.load() to decide
    whether a row needs re-enriching; an empty history just means every row
    looks new, which is exactly what a stateless smoke run should do. All of
    them call store.write_raw() as they go, which this test must not let
    write to the real data/raw/ directory as a side effect of running tests."""

    def load(self, source_key: str) -> dict[str, RegulatoryDocument]:
        return {}

    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


async def _live_docs(source: SourceConfig) -> list[RegulatoryDocument]:
    scraper_cls = get_scraper(source.scraper)
    async with HttpClient(
        user_agent="saudi-law-tracker-smoke-test/0.1 (+research)",
        timeout=source.timeout,
        max_retries=source.max_retries,
        request_delay=source.request_delay,
    ) as http:
        scraper = scraper_cls(source, http, _DiscardingStore())  # type: ignore[arg-type]
        docs: AsyncIterator[RegulatoryDocument] = scraper.discover()
        return [doc async for doc in docs]


def _is_verified_and_dated(doc: RegulatoryDocument) -> bool:
    """"Dated" here means *any* real timestamp the scraper actually read off
    the live page -- a true publication date when the source has one, or
    `last_modified` for a source like zatca that (per SLT-09) only ever has
    a page-edit timestamp available. Either is proof the scraper is still
    correctly parsing real content from the live site, which is this
    smoke test's actual job; it is not this test's place to also assert a
    source has a real issuance date, only that it hasn't gone silent."""

    has_a_real_date = (
        doc.published_gregorian is not None
        or doc.published_hijri is not None
        or doc.last_modified is not None
    )
    return doc.verified and has_a_real_date


def _enabled_sources() -> list[SourceConfig]:
    return [s for s in load_sources() if s.enabled]


@pytest.mark.parametrize("source", _enabled_sources(), ids=lambda s: s.key)
def test_enabled_source_returns_at_least_one_verified_dated_row(
    source: SourceConfig,
) -> None:
    docs = asyncio.run(_live_docs(source))
    verified_dated = [d for d in docs if _is_verified_and_dated(d)]

    assert verified_dated, (
        f"{source.key}: live scrape found {len(docs)} row(s), none both "
        "verified and dated. Either this source's selectors have drifted "
        "out from under the live site's real markup (SLT-03), or the site "
        "itself is currently down/changed -- check logs/ and `status` "
        "before assuming it's the scraper."
    )
