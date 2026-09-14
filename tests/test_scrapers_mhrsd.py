from __future__ import annotations

import asyncio
from typing import Any

from selectolax.parser import HTMLParser

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.mhrsd import MhrsdScraper, _is_labor_related

_POLICIES_PAGE = """
<div class="policy-list">
  <div class="policy-card">
    <a href="/ar/policies/labor-law">نظام العمل</a>
    <span>محدث بتاريخ 1445/01/10 هـ</span>
  </div>
  <div class="policy-card">
    <p>no link here</p>
  </div>
</div>
"""

_NEWS_PAGE = """
<div class="news-list">
  <div class="news-card">
    <a href="/ar/news/labor-law-amendment-2025">تعديل نظام العمل بشأن نهاية الخدمة</a>
    <span class="news-card__date">1446/05/02 هـ</span>
  </div>
  <div class="news-card">
    <a href="/ar/news/minister-visits-riyadh">الوزير يزور مكتب العمل بالرياض</a>
    <span class="news-card__date">1446/05/01 هـ</span>
  </div>
  <div class="news-card">
    <p>no link here</p>
  </div>
</div>
"""


def _scraper() -> MhrsdScraper:
    source = SourceConfig(
        key="mhrsd_labor",
        name="MHRSD",
        scraper="mhrsd",
        base_url="https://www.hrsd.gov.sa",
        start_paths=["/ar/policies"],
        categories=["regulation"],
    )
    return MhrsdScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_is_labor_related_matches_expected_keywords():
    assert _is_labor_related("تعديل نظام العمل بشأن نهاية الخدمة")
    assert _is_labor_related("صدور لائحة تنفيذية جديدة")
    assert not _is_labor_related("الوزير يزور مكتب العمل بالرياض")


def test_parse_policy_card_extracts_title_url_and_date():
    card = HTMLParser(_POLICIES_PAGE).css(".policy-card")[0]
    doc = _scraper()._parse_policy_card(card)

    assert doc is not None
    assert doc.title == "نظام العمل"
    assert doc.doc_type == DocumentType.REGULATION
    assert str(doc.url) == "https://www.hrsd.gov.sa/ar/policies/labor-law"
    assert doc.published_hijri == "1445-01-10"
    assert doc.verified is True


def test_parse_policy_card_without_link_is_skipped():
    card = HTMLParser(_POLICIES_PAGE).css(".policy-card")[1]
    assert _scraper()._parse_policy_card(card) is None


def test_parse_news_card_keeps_labor_related_items():
    card = HTMLParser(_NEWS_PAGE).css(".news-card")[0]
    doc = _scraper()._parse_news_card(card)

    assert doc is not None
    assert doc.title == "تعديل نظام العمل بشأن نهاية الخدمة"
    assert doc.doc_type == DocumentType.MINISTERIAL_DECISION
    assert doc.published_hijri == "1446-05-02"
    assert doc.verified is True


def test_parse_news_card_drops_unrelated_items():
    card = HTMLParser(_NEWS_PAGE).css(".news-card")[1]
    assert _scraper()._parse_news_card(card) is None


def test_parse_news_card_without_link_is_skipped():
    card = HTMLParser(_NEWS_PAGE).css(".news-card")[2]
    assert _scraper()._parse_news_card(card) is None


class _FakeHttp:
    async def get(self, url: str, **kwargs: object) -> Any:
        class _Resp:
            text = _POLICIES_PAGE if "polic" in url else _NEWS_PAGE

        return _Resp()


class _NullStore:
    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


def test_discover_dispatches_by_path():
    """`/policies` and `/news` paths should hit their own parsers, not each other's."""

    scraper = _scraper()
    scraper.source.start_paths = ["/ar/policies", "/ar/media-center/ministry-news"]
    scraper.http = _FakeHttp()  # type: ignore[assignment]
    scraper.store = _NullStore()  # type: ignore[assignment]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())
    titles = {d.title for d in docs}
    assert "نظام العمل" in titles
    assert "تعديل نظام العمل بشأن نهاية الخدمة" in titles
    assert "الوزير يزور مكتب العمل بالرياض" not in titles
