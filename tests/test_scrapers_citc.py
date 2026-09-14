from __future__ import annotations

from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType
from saudi_law_tracker.scrapers.citc import CitcScraper

# A saved (hand-reduced) shape of the __NEXT_DATA__ blob a Next.js regulations
# listing page embeds at the bottom of the document.
_NEXT_DATA_PAGE = """
<html>
<body>
<div id="__next"></div>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "items": [
        {
          "title": "Cybersecurity Regulatory Framework",
          "slug": "cybersecurity-regulatory-framework",
          "category": "framework",
          "date": "2024-03-10"
        },
        {
          "title": "Draft Spectrum Fees Regulation",
          "slug": "draft-spectrum-fees",
          "category": "public-consultation",
          "publishedAt": "2025-01-05T00:00:00Z"
        },
        {
          "titleAr": "لائحة تراخيص الاتصالات",
          "id": "telecom-licensing-2022"
        },
        {
          "category": "regulation"
        }
      ]
    }
  }
}
</script>
</body>
</html>
"""


def _scraper() -> CitcScraper:
    source = SourceConfig(
        key="citc",
        name="CST",
        scraper="citc",
        base_url="https://www.cst.gov.sa",
        start_paths=["/en/regulations"],
        categories=["regulation"],
    )
    return CitcScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_extract_items_reads_next_data_blob():
    items = CitcScraper._extract_items(_NEXT_DATA_PAGE)
    assert len(items) == 4


def test_extract_items_returns_empty_list_without_next_data():
    assert CitcScraper._extract_items("<html><body>no data here</body></html>") == []


def test_parse_item_framework_gets_framework_type_and_iso_date():
    items = CitcScraper._extract_items(_NEXT_DATA_PAGE)
    doc = _scraper()._parse_item(items[0], "/en/regulations")

    assert doc is not None
    assert doc.title == "Cybersecurity Regulatory Framework"
    assert doc.doc_type == DocumentType.FRAMEWORK
    assert doc.published_gregorian == date(2024, 3, 10)
    assert str(doc.url) == "https://www.cst.gov.sa/en/regulations/cybersecurity-regulatory-framework"
    assert doc.verified is True


def test_parse_item_consultation_category_is_public_consultation():
    items = CitcScraper._extract_items(_NEXT_DATA_PAGE)
    doc = _scraper()._parse_item(items[1], "/en/regulations")

    assert doc is not None
    assert doc.doc_type == DocumentType.PUBLIC_CONSULTATION
    assert doc.published_gregorian == date(2025, 1, 5)


def test_parse_item_falls_back_to_arabic_title_and_id_as_slug():
    items = CitcScraper._extract_items(_NEXT_DATA_PAGE)
    doc = _scraper()._parse_item(items[2], "/en/regulations")

    assert doc is not None
    assert doc.title == "لائحة تراخيص الاتصالات"
    assert str(doc.url) == "https://www.cst.gov.sa/en/regulations/telecom-licensing-2022"


def test_parse_item_without_title_is_skipped():
    items = CitcScraper._extract_items(_NEXT_DATA_PAGE)
    assert _scraper()._parse_item(items[3], "/en/regulations") is None
