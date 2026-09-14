# ruff: noqa: E501 -- real captured markup below has some genuinely long
# lines; wrapping them would mean editing bytes that are supposed to be a
# faithful copy of the live page.
from __future__ import annotations

import asyncio
from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.sama import SamaScraper, _site_path

# Trimmed copy of the actual saved snapshot in data/raw/sama_circulars/
# (20260914T135934Z__rest_p0.html) -- this is what the REST endpoint
# actually returns (HTTP 200, Content-Type: text/html) instead of JSON for
# every regulatory-content path on the site right now. The only change from
# the saved bytes: the header's large embedded base64 logo `<img>` (~30KB,
# irrelevant to the "Something went wrong" check) elided. The mismatched
# <p>...<p>...</p></p> nesting below is a real quirk of SAMA's own error
# template (kept as saved), not a typo here -- harmless for this check,
# since discover() only does a plain substring search, never parses the DOM.
_SAMA_ERROR_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta content="text/html; charset=utf-8" http-equiv="Content-Type">
<title>البنك المركزي السعودي | Saudi Central Bank</title>
</head>
<body>
<header>
<!-- real page has a large embedded base64 logo image here, elided -->
</header>
    <section dir="rtl" class="sidebar">
        <p>
        <label>عزيزي المستفيد ،</label>
        حدث خطأ ما في طلبك، نرجو تزويدنا بمعلومات الطلب عن طريق إرسال الرقم التالي : <span style="display:block">16469394093192074089</span> على البريد الالكتروني للدعم الفني:
        <span>SAMASD@SAMA.GOV.SA</span>
        <div>نشكر لكم تفهمكم ..</div>
        </p>
    </section>
    <section class="content">
        <p><label>Dear beneficiary,</label>Something went wrong in your request, please provide us with the request details by sending the following ID: <span>16469394093192074089</span>
<p style="display:block">to the help-desk email: <span>SAMASD@SAMA.GOV.SA</span></p>
<div>Thank you for your understanding.</div>
</p></section><div class="separator"></div><section class="content box"><label>Return to the previous page</label><div><a href="javascript:history.back()">Back</a></div></section><section dir="rtl" class="sidebar box"><label>للعودة للصفحة السابقة</label><div><a href="javascript:history.back()">عودة</a></div></section></div>
</body>
</html>
"""

# A saved (hand-reduced) shape of what SAMA's SharePoint list REST endpoint
# returns in its "verbose" OData envelope: `{"d": {"results": [...]}}`.
_REST_RESPONSE = """
{
  "d": {
    "results": [
      {
        "Id": 501,
        "Title": "تعميم بشأن متطلبات الحوكمة لدى البنوك",
        "CircularNumber": "44047144",
        "HijriDate": "1444/07/14",
        "IssueDate": "2023-02-05T00:00:00Z",
        "DocumentUrl": {
          "Url": "https://www.sama.gov.sa/ar-sa/Laws/BankingRules/Circular-44047144.pdf",
          "Description": "Circular PDF"
        }
      },
      {
        "Id": 502,
        "Title": "تعميم بدون تاريخ هجري",
        "IssueDate": "2024-06-11T00:00:00Z"
      },
      {
        "Id": 503,
        "Title": "تعميم بدون رابط"
      },
      {
        "Id": 504
      },
      {
        "Id": 505,
        "Title": "تعميم بتاريخ تعديل فقط",
        "Modified": "2025-03-10T00:00:00Z"
      }
    ]
  }
}
"""


def _scraper() -> SamaScraper:
    source = SourceConfig(
        key="sama_circulars",
        name="SAMA",
        scraper="sama",
        base_url="https://www.sama.gov.sa",
        start_paths=["/ar-sa/Laws/Pages/default.aspx"],
        categories=["circular"],
    )
    return SamaScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_site_path_strips_the_pages_segment():
    assert _site_path("/ar-sa/Laws/Pages/default.aspx") == "/ar-sa/Laws"
    assert _site_path("/no-pages-segment") == "/no-pages-segment"


def test_extract_items_reads_verbose_odata_envelope():
    items = SamaScraper._extract_items(_REST_RESPONSE)
    assert len(items) == 5


def test_extract_items_returns_empty_list_on_bad_json():
    assert SamaScraper._extract_items("not json") == []


def test_parse_item_extracts_title_ref_dates_and_url():
    items = SamaScraper._extract_items(_REST_RESPONSE)
    doc = _scraper()._parse_item(items[0])

    assert doc is not None
    assert doc.title == "تعميم بشأن متطلبات الحوكمة لدى البنوك"
    assert doc.doc_type == DocumentType.CIRCULAR
    assert doc.reference_number == "44047144"
    assert doc.published_hijri == "1444-07-14"
    assert doc.published_gregorian == date(2023, 2, 5)  # from the Hijri text, not IssueDate
    assert str(doc.url) == "https://www.sama.gov.sa/ar-sa/Laws/BankingRules/Circular-44047144.pdf"
    assert doc.verified is True


def test_parse_item_falls_back_to_iso_date_without_hijri():
    items = SamaScraper._extract_items(_REST_RESPONSE)
    doc = _scraper()._parse_item(items[1])

    assert doc is not None
    assert doc.published_hijri is None
    assert doc.published_gregorian == date(2024, 6, 11)


def test_parse_item_falls_back_to_dispform_url_without_link_field():
    items = SamaScraper._extract_items(_REST_RESPONSE)
    doc = _scraper()._parse_item(items[2])

    assert doc is not None
    assert "DispForm.aspx?ID=503" in str(doc.url)


def test_parse_item_without_title_is_skipped():
    items = SamaScraper._extract_items(_REST_RESPONSE)
    assert _scraper()._parse_item(items[3]) is None


def test_parse_item_modified_field_is_last_modified_not_published():
    """SharePoint's own "Modified" list-item edit timestamp must never stand
    in for the circular's real issuance date (SLT-09)."""

    items = SamaScraper._extract_items(_REST_RESPONSE)
    doc = _scraper()._parse_item(items[4])

    assert doc is not None
    assert doc.last_modified == date(2025, 3, 10)
    assert doc.published_gregorian is None
    assert doc.published_hijri is None


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeHttp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requested: list[str] = []

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.requested.append(url)
        return _FakeResponse(self.text)


class _FakeStore:
    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


def test_discover_stops_cleanly_on_sama_error_page():
    """The REST call can 200 with SAMA's own generic error page instead of
    JSON; discover() must treat that as "nothing here" and stop, not loop
    through every page hitting the same error."""

    source = SourceConfig(
        key="sama_circulars",
        name="SAMA",
        scraper="sama",
        base_url="https://www.sama.gov.sa",
        start_paths=["/ar-sa/Laws/Pages/default.aspx"],
        categories=["circular"],
    )
    http = _FakeHttp(_SAMA_ERROR_PAGE)
    scraper = SamaScraper(source, http, _FakeStore())  # type: ignore[arg-type]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())

    assert docs == []
    assert len(http.requested) == 1  # stopped after page 1, not max_pages requests
