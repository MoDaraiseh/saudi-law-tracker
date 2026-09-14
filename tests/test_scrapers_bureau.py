from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from selectolax.parser import HTMLParser, Node

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
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


def _node(html: str, selector: str = "div.search_result_item") -> Node:
    node = HTMLParser(html).css_first(selector)
    assert node is not None
    return node


def _draft(scraper: BureauOfExpertsScraper, html: str) -> RegulatoryDocument:
    doc = scraper._parse_row(_node(html))
    assert doc is not None
    return doc


def test_parse_row_extracts_title_url_dates_and_type():
    doc = _draft(_scraper(), _ROW)

    assert doc.title == "نظام التنفيذ"
    assert str(doc.url) == "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/abc-123/1"
    assert doc.doc_type == DocumentType.LAW
    assert doc.published_hijri == "1447-11-03"
    assert doc.published_gregorian == date(2026, 4, 20)
    assert doc.effective_date == date(2026, 5, 1)
    assert doc.summary and "1433" in doc.summary


def test_parse_row_without_link_is_skipped():
    node = _node("<div class='search_result_item'><p>no link</p></div>", "div")
    assert _scraper()._parse_row(node) is None


# --------------------------------------------------------------------------
# LawDetails enrichment: reference_number / pdf_urls
# --------------------------------------------------------------------------

#: Trimmed real excerpt -- confirmed live 2026-09-14 against a real
#: LawDetails page. `table.table-details` occurs zero times anywhere on the
#: site, and no link anywhere ends in `.pdf`; the real reference number is a
#: free-text sentence in `h4.center`, and the real (direct, confirmed
#: `application/pdf`) download link matches `a[href*="/Files/Download/"]`
#: -- not the `/BoeLaws/Laws/Viewer/` link, which looks like "the" original
#: document but actually resolves to an HTML viewer page.
_DETAIL_PAGE = """
<html><body>
  <h3 class="center">نظام التنفيذ</h3>
  <h3 class="center">1447 هـ</h3>
  <h4 class="center">مرسوم ملكي رقم (م/237) وتاريخ 1447/11/3هـ</h4>
  <p>نص النظام...</p>
  <a href="/BoeLaws/Laws/Viewer/212d6cb4-2186-4f67-aa7a-b44700a9ac8a?lawId=x"
     target="_blank">اصل الوثيقة</a>
  <a href="/Files/Download/?attId=fd994824-0c2c-4423-b86d-b49d00d779eb"
     target="_blank">Translated document</a>
  <a href="/some/other/page">رابط عادي</a>
</body></html>
"""

#: Real second form, confirmed live on a different law: no parens, "ب"
#: instead of "و" before "تاريخ", and spaces inside the reference itself.
_DETAIL_PAGE_NO_PARENS = """
<html><body>
  <h4 class="center">مرسوم ملكي رقم م / 113 بتاريخ 2 / 11 / 1438</h4>
  <a href="/Files/Download/?attId=7db4e0d9-d979-4ae0-810f-adbb0111144f"
     target="_blank">Translated document</a>
</body></html>
"""

#: Real case where a decree heading is followed by the Council of Ministers
#: resolution it approves -- the first heading is this document's own.
_DETAIL_PAGE_TWO_HEADINGS = """
<html><body>
  <h4 class="center">مرسوم ملكي رقم (م/237) وتاريخ 1447/11/3هـ</h4>
  <h4 class="center">قرار مجلس الوزراء رقم (746) وتاريخ 1447/10/26هـ</h4>
</body></html>
"""


def test_parse_details_extracts_reference_number_and_pdf_link():
    reference_number, pdf_urls = _scraper()._parse_details(_DETAIL_PAGE)

    assert reference_number == "م/237"
    assert pdf_urls == [
        "https://laws.boe.gov.sa/Files/Download/?attId=fd994824-0c2c-4423-b86d-b49d00d779eb",
    ]


def test_parse_details_handles_missing_heading_and_download_link():
    reference_number, pdf_urls = _scraper()._parse_details("<html><body>nothing here</body></html>")

    assert reference_number is None
    assert pdf_urls == []


def test_parse_details_handles_reference_without_parens():
    reference_number, _ = _scraper()._parse_details(_DETAIL_PAGE_NO_PARENS)
    assert reference_number == "م / 113"


def test_parse_details_uses_first_heading_when_more_than_one():
    reference_number, _ = _scraper()._parse_details(_DETAIL_PAGE_TWO_HEADINGS)
    assert reference_number == "م/237"  # this document's own decree, not the resolution it approves


def test_parse_details_ignores_viewer_links_as_pdf_urls():
    """`/BoeLaws/Laws/Viewer/...` looks like "the" original document link but
    resolves to an HTML viewer page, not a PDF -- confirmed live -- so it
    must never end up in pdf_urls even when it's the only link on the page."""

    html = """
    <html><body>
      <h4 class="center">مرسوم ملكي رقم (م/1) وتاريخ 1440/1/1هـ</h4>
      <a href="/BoeLaws/Laws/Viewer/aaa?lawId=bbb">اصل الوثيقة</a>
    </body></html>
    """
    _, pdf_urls = _scraper()._parse_details(html)
    assert pdf_urls == []


def test_enrich_recomputes_content_hash_with_new_fields():
    draft = _draft(_scraper(), _ROW)

    enriched = _scraper()._enrich(draft, "م/132", ["https://laws.boe.gov.sa/x.pdf"])

    assert enriched.uid == draft.uid  # same document identity
    assert enriched.reference_number == "م/132"
    assert [str(u) for u in enriched.pdf_urls] == ["https://laws.boe.gov.sa/x.pdf"]
    assert enriched.verified is True
    # the hash must reflect the newly-populated fields, or upsert_many would
    # never see this as a real change once it's persisted
    assert enriched.content_hash != draft.content_hash


# --------------------------------------------------------------------------
# Deciding whether a row is worth a LawDetails request
# --------------------------------------------------------------------------


def test_needs_detail_fetch_true_for_a_brand_new_row():
    draft = _draft(_scraper(), _ROW)
    assert _scraper()._needs_detail_fetch(draft, None) is True


def test_needs_detail_fetch_false_for_unchanged_unenriched_row_outside_backfill():
    draft = _draft(_scraper(), _ROW)
    existing = _draft(_scraper(), _ROW)  # independent parse, identical content, still unenriched

    assert _scraper()._needs_detail_fetch(draft, existing) is False


def test_needs_detail_fetch_true_when_listing_content_changed():
    draft = _draft(_scraper(), _ROW)

    changed_html = _ROW.replace("نظام التنفيذ", "نظام التنفيذ المعدل")
    existing = _draft(_scraper(), changed_html)  # same URL/date, different title -> same uid

    assert existing.uid == draft.uid
    assert _scraper()._needs_detail_fetch(draft, existing) is True


def test_needs_detail_fetch_false_for_already_enriched_row_even_though_fields_differ():
    draft = _draft(_scraper(), _ROW)
    scraper = _scraper()
    existing = scraper._enrich(draft, "م/1", ["https://laws.boe.gov.sa/x.pdf"])

    # existing's content_hash differs from draft's (draft has no ref/pdf yet),
    # but that's only because draft hasn't fetched details -- not a real change.
    assert existing.content_hash != draft.content_hash
    assert scraper._needs_detail_fetch(draft, existing) is False


def test_needs_detail_fetch_backfill_refetches_unenriched_row():
    draft = _draft(_scraper(), _ROW)
    existing = _draft(_scraper(), _ROW)  # unchanged, still unenriched

    scraper = _scraper()
    scraper.backfill = True
    assert scraper._needs_detail_fetch(draft, existing) is True


def test_needs_detail_fetch_backfill_skips_already_enriched_row():
    draft = _draft(_scraper(), _ROW)
    scraper = _scraper()
    existing = scraper._enrich(draft, "م/1", ["https://laws.boe.gov.sa/x.pdf"])
    scraper.backfill = True

    assert scraper._needs_detail_fetch(draft, existing) is False


# --------------------------------------------------------------------------
# discover(): pagination cap, selective enrichment, and --backfill
# --------------------------------------------------------------------------


def _row_html(guid: str, title: str) -> str:
    return f"""
    <div class="search_result_item">
      <a class="result-keyword-title" href="/BoeLaws/Laws/LawDetails/{guid}/1">{title}</a>
      <p class="result-keyword-desc">وصف {title}</p>
      <span>تاريخ الإصدار: 1447/11/03 هـ</span>
      <span>تاريخ النشر: 1447/11/14 هـ</span>
    </div>
    """


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeHttp:
    """Serves canned listing pages by PageNumber and canned detail pages by guid."""

    def __init__(self, pages: dict[int, str], details: dict[str, str]) -> None:
        self.pages = pages
        self.details = details
        self.page_requests: list[int] = []
        self.detail_requests: list[str] = []

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        if "LawDetails" in url:
            guid = url.rstrip("/").split("/")[-2]
            self.detail_requests.append(guid)
            return _FakeResponse(self.details.get(guid, "<html></html>"))

        match = re.search(r"PageNumber=(\d+)", url)
        page = int(match.group(1)) if match else 1
        self.page_requests.append(page)
        return _FakeResponse(self.pages.get(page, ""))


class _FakeStore:
    def __init__(self, known: dict[str, RegulatoryDocument]) -> None:
        self._known = known

    def load(self, source_key: str) -> dict[str, RegulatoryDocument]:
        return dict(self._known)

    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


def _build_scraper_with(
    pages: dict[int, str],
    details: dict[str, str],
    known: dict[str, RegulatoryDocument],
    *,
    backfill: bool,
) -> tuple[BureauOfExpertsScraper, _FakeHttp]:
    source = SourceConfig(
        key="bureau_of_experts",
        name="Bureau of Experts",
        scraper="bureau_of_experts",
        base_url="https://laws.boe.gov.sa",
        start_paths=["/BoeLaws/Laws/Search"],
        categories=["law"],
    )
    http = _FakeHttp(pages, details)
    store = _FakeStore(known)
    scraper = BureauOfExpertsScraper(source, http, store, backfill=backfill)  # type: ignore[arg-type]
    return scraper, http


def _run_discover(scraper: BureauOfExpertsScraper) -> list[RegulatoryDocument]:
    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    return asyncio.run(collect())


def _detail_html_for(guid: str) -> str:
    heading = f'<h4 class="center">مرسوم ملكي رقم REF-{guid} وتاريخ 1447/1/1هـ</h4>'
    link = f'<a href="/Files/Download/?attId={guid}">تحميل</a>'
    return heading + link


def test_discover_normal_run_caps_pages_and_only_enriches_new_or_changed_rows():
    parser = _scraper()
    changed_old = _draft(parser, _row_html("changed-guid", "نظام قديم"))
    stable_unenriched = _draft(parser, _row_html("stable-unenriched-guid", "نظام مستقر واحد"))
    stable_enriched_draft = _draft(parser, _row_html("stable-enriched-guid", "نظام مستقر اثنان"))
    stable_enriched = parser._enrich(stable_enriched_draft, "REF-EXISTING", ["https://x/e.pdf"])

    known = {
        changed_old.uid: changed_old,
        stable_unenriched.uid: stable_unenriched,
        stable_enriched.uid: stable_enriched,
    }
    pages = {
        1: _row_html("new-guid", "نظام جديد") + _row_html("changed-guid", "نظام معدل"),
        2: (
            _row_html("stable-unenriched-guid", "نظام مستقر واحد")
            + _row_html("stable-enriched-guid", "نظام مستقر اثنان")
        ),
        3: _row_html("page3-guid", "نظام صفحة ثلاثة"),
        4: _row_html("page4-guid", "نظام صفحة اربعة"),  # beyond max_pages=3
    }
    details: dict[str, Any] = {
        "new-guid": _detail_html_for("new-guid"),
        "changed-guid": _detail_html_for("changed-guid"),
        "page3-guid": _detail_html_for("page3-guid"),
    }

    scraper, http = _build_scraper_with(pages, details, known, backfill=False)
    docs = _run_discover(scraper)

    assert http.page_requests == [1, 2, 3]  # capped at max_pages=3, page 4 never requested
    assert set(http.detail_requests) == {"new-guid", "changed-guid", "page3-guid"}

    by_title = {d.title: d for d in docs}
    assert by_title["نظام جديد"].reference_number == "REF-new-guid"
    assert by_title["نظام معدل"].reference_number == "REF-changed-guid"
    unenriched_row = by_title["نظام مستقر واحد"]
    assert unenriched_row.reference_number is None  # unchanged & unenriched: left alone
    assert by_title["نظام مستقر اثنان"].reference_number == "REF-EXISTING"  # carried forward


def test_discover_backfill_walks_past_max_pages_and_enriches_old_rows():
    parser = _scraper()
    stable_unenriched = _draft(parser, _row_html("page4-guid", "نظام صفحة اربعة"))

    known = {stable_unenriched.uid: stable_unenriched}
    pages = {
        1: _row_html("p1-guid", "نظام واحد"),
        2: _row_html("p2-guid", "نظام اثنان"),
        3: _row_html("p3-guid", "نظام ثلاثة"),
        4: _row_html("page4-guid", "نظام صفحة اربعة"),  # already known, unenriched
        5: "",  # empty page ends the walk
    }
    guids = ("p1-guid", "p2-guid", "p3-guid", "page4-guid")
    details = {guid: _detail_html_for(guid) for guid in guids}

    scraper, http = _build_scraper_with(pages, details, known, backfill=True)
    docs = _run_discover(scraper)

    assert http.page_requests == [1, 2, 3, 4, 5]  # walked past the normal 3-page cap
    assert "page4-guid" in http.detail_requests  # backfill re-fetched the old, unenriched row

    by_title = {d.title: d for d in docs}
    assert by_title["نظام صفحة اربعة"].reference_number == "REF-page4-guid"
