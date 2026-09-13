from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType
from saudi_law_tracker.scrapers.bureau_of_experts import BureauOfExpertsScraper

_ROW = """
<div class="search_result_item">
  <a class="result-keyword-title" href="/BoeLaws/Laws/LawDetails/abc-123/1">نظام التنفيذ</a>
  <p class="result-keyword-desc">يحل هذا النظام محل نظام التنفيذ لعام 1433هـ.</p>
  <div class="d-flex">
    <span>تاريخ الإصـــدار: <strong>1447/11/03 هـ</strong></span>
    <span>تاريخ النشر: <strong>1447/11/14 هـ</strong></span>
  </div>
</div>
"""


def _scraper() -> BureauOfExpertsScraper:
    source = SourceConfig(
        key="bureau_of_experts",
        name="Bureau of Experts",
        scraper="bureau_of_experts",
        base_url="https://laws.boe.gov.sa",
        start_paths=["/BoeLaws/Laws/Search"],
        categories=["law"],
    )
    return BureauOfExpertsScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_parse_row_extracts_title_url_dates_and_type():
    node = HTMLParser(_ROW).css_first("div.search_result_item")
    assert node is not None
    doc = _scraper()._parse_row(node)

    assert doc is not None
    assert doc.title == "نظام التنفيذ"
    assert str(doc.url) == "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/abc-123/1"
    assert doc.doc_type == DocumentType.LAW
    assert doc.published_hijri == "1447-11-03"
    assert doc.published_gregorian == date(2026, 4, 20)
    assert doc.effective_date == date(2026, 5, 1)
    assert doc.summary and "1433" in doc.summary


def test_parse_row_without_link_is_skipped():
    node = HTMLParser("<div class='search_result_item'><p>no link</p></div>").css_first("div")
    assert node is not None
    assert _scraper()._parse_row(node) is None
