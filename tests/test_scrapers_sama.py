from __future__ import annotations

from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType
from saudi_law_tracker.scrapers.sama import SamaScraper, _site_path

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
    assert len(items) == 4


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
