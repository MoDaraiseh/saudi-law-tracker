from __future__ import annotations

import asyncio
import re
from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.umm_al_qura import UmmAlQuraScraper

# ruff: noqa: E501 -- real captured markup below has a couple of genuinely
# long lines (data: URLs would be worse; these are just long query strings);
# wrapping them would mean editing bytes that are supposed to be a faithful
# copy of the live page.

# Trimmed copy of the actual saved snapshot in data/raw/umm_al_qura/
# (first two rows, from the 2026-09-14 13:59 run):
#   20260914T135937Z__p1.html
# against www.uqn.gov.sa/archive. `#issuesTable` (the previous config's
# selector) doesn't exist anywhere on the site; `/Pages/Issues.aspx` 404s
# outright, and that 404 page is itself ~746KB (see umm_al_qura.py's
# docstring). The only change from the saved bytes: the template's
# indentation collapsed to one-tag-per-line -- meaning-preserving (HTML
# whitespace between tags isn't significant), not a content change.

_ARCHIVE_PAGE = """
<div class="ummalqura-archive-pagination">
<div class="content row">
<a href="/digital?date=2026-09-11" class="article-wrapper" title="uploads/pdf/2026/09/11/ummalqura_pdf-20260911-1.pdf?ts=193509">
<div class="article-image">
<div class="relative layout-ratio contain-ratio">
<img src="https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/09/11/ummalqura_pdf-20260911-1.jpg&amp;ts=193509" data-image="https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/09/11/ummalqura_pdf-20260911-1.jpg&amp;ts=193509" alt="العدد 5182">
</div>
</div>
<h2 class="article-title">العدد 5182</h2>
</a>
<a href="/digital?date=2026-09-08" class="article-wrapper" title="uploads/pdf/2026/09/08/ummalqura_pdf-20260908-2.pdf?ts=220707">
<div class="article-image">
<div class="relative layout-ratio contain-ratio">
<img src="https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/09/08/ummalqura_pdf-20260908-1.jpg&amp;ts=204255&amp;ts=220707" data-image="https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/09/08/ummalqura_pdf-20260908-1.jpg&amp;ts=204255&amp;ts=220707" alt="العدد 5181">
</div>
</div>
<h2 class="article-title">العدد 5181</h2>
</a>
</div>
</div>
"""

_EMPTY_PAGE = "<html><body>no archive widget on this page</body></html>"


def _scraper(start_paths: list[str] | None = None) -> UmmAlQuraScraper:
    source = SourceConfig(
        key="umm_al_qura",
        name="Umm Al-Qura",
        scraper="umm_al_qura",
        base_url="https://www.uqn.gov.sa",
        start_paths=start_paths or ["/archive"],
        categories=["gazette_issue"],
    )
    return UmmAlQuraScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_extract_items_reads_real_archive_widget():
    items = UmmAlQuraScraper._extract_items(_ARCHIVE_PAGE)
    assert len(items) == 2


def test_extract_items_returns_empty_list_without_widget():
    assert UmmAlQuraScraper._extract_items(_EMPTY_PAGE) == []


def test_parse_item_reads_date_from_href_query_param():
    items = UmmAlQuraScraper._extract_items(_ARCHIVE_PAGE)
    doc = _scraper()._parse_item(items[0])

    assert doc is not None
    assert doc.title == "جريدة أم القرى - العدد 5182"
    assert doc.doc_type == DocumentType.GAZETTE_ISSUE
    assert doc.reference_number == "5182"
    assert doc.published_gregorian == date(2026, 9, 11)
    assert doc.published_hijri is None  # not given anywhere on this page
    assert str(doc.url) == "https://www.uqn.gov.sa/digital?date=2026-09-11"
    assert doc.verified is True


def test_parse_item_builds_real_cdn_pdf_url_not_the_bare_storage_path():
    items = UmmAlQuraScraper._extract_items(_ARCHIVE_PAGE)
    doc = _scraper()._parse_item(items[0])

    assert doc is not None
    assert doc.pdf_urls
    assert str(doc.pdf_urls[0]) == (
        "https://www.uqn.gov.sa/cdn/?url=uploads/pdf/2026/09/11/"
        "ummalqura_pdf-20260911-1.pdf&ts=193509"
    )


def test_parse_item_second_row_gets_its_own_issue_number_and_date():
    items = UmmAlQuraScraper._extract_items(_ARCHIVE_PAGE)
    doc = _scraper()._parse_item(items[1])

    assert doc is not None
    assert doc.reference_number == "5181"
    assert doc.published_gregorian == date(2026, 9, 8)


def test_parse_item_without_title_link_is_skipped():
    items = UmmAlQuraScraper._extract_items(_ARCHIVE_PAGE)
    row = items[0]
    title_node = row.css_first(".article-title")
    assert title_node is not None
    title_node.decompose()
    assert _scraper()._parse_item(row) is None


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeHttp:
    def __init__(self, pages: list[str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.requested.append(url)
        match = re.search(r"pgno=(\d+)", url)
        page = int(match.group(1)) if match else 1
        text = self.pages[page - 1] if page - 1 < len(self.pages) else ""
        return _FakeResponse(text)


class _FakeStore:
    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


def test_discover_stops_paginating_once_a_page_returns_no_items():
    """Page 1 and 2 have real items, page 3 is empty -- discover() should
    stop there instead of exhausting max_pages regardless."""

    http = _FakeHttp([_ARCHIVE_PAGE, _ARCHIVE_PAGE, _EMPTY_PAGE])
    scraper = _scraper()
    scraper.http = http  # type: ignore[assignment]
    scraper.store = _FakeStore()  # type: ignore[assignment]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())

    assert len(docs) == 4  # 2 items x 2 real pages
    assert len(http.requested) == 3  # page 1, 2, and the empty page 3 that stopped it
