from __future__ import annotations

import asyncio
from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.zatca import ZatcaScraper, _parse_last_modified

# Saved (hand-reduced) real shapes fetched live from zatca.gov.sa on 2026-09-14 --
# see zatca.py's docstring for how these were found.

# GET /en/_LAYOUTS/15/GAZTInternet/PortalHandler.ashx
#     ?op=LoadItems&listUrl=/en/RulesRegulations/Taxes/Pages&viewName=Home
_TAXES_API_RESPONSE = """
[
  {"DocIcon": "aspx", "LinkFilename": "ZakatRegulations.aspx", "Category": "Zakat",
   "Title": "The Implementing Regulation for Zakat Collection", "Visibility": "1",
   "FileLeafRef": "ZakatRegulations.aspx", "ID": 2},
  {"DocIcon": "aspx", "LinkFilename": "CalculateZakat.aspx", "Category": "Zakat",
   "Title": "Calculation rules of Zakat levied upon financing activities", "Visibility": "0",
   "FileLeafRef": "CalculateZakat.aspx", "ID": 3},
  {"DocIcon": "aspx", "LinkFilename": "default.aspx", "Category": "",
   "Title": "Zakat, Customs, and Tax Regulations", "Visibility": "1",
   "FileLeafRef": "default.aspx", "ID": 1}
]
"""

# The same endpoint for a list whose SharePoint view doesn't support "Home"
# (confirmed live for VAT and InformationExchange).
_INVALID_VIEW_RESPONSE = """
{"Message": "Unexpected error has occurred. The specified view is invalid."}
"""

# GET /en/RulesRegulations/Taxes/Pages/ZakatRegulations.aspx (trimmed)
_LEAF_PAGE_WITH_DATE = """
<html><body>
<div id="ctl00_ucLastModifiedDate_lastUpdateDiv" class="home-lastupdate-container">
    <div class="container">
        <div class="text-end py-4">
            <p class="fs-14">
                Last Update:

                26 Aug 2026 04:47 PM

                Saudi Arabia Time
            </p>
        </div>
    </div>
</div>
</body></html>
"""

_LEAF_PAGE_WITHOUT_DATE = "<html><body><p>Page not found</p></body></html>"


def _scraper() -> ZatcaScraper:
    source = SourceConfig(
        key="zatca_updates",
        name="ZATCA",
        scraper="zatca",
        base_url="https://zatca.gov.sa",
        categories=["tax_ruling"],
    )
    return ZatcaScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_extract_items_filters_hidden_and_index_page():
    items = ZatcaScraper._extract_items(_TAXES_API_RESPONSE)
    assert len(items) == 1
    assert items[0]["Title"] == "The Implementing Regulation for Zakat Collection"


def test_extract_items_handles_invalid_view_error_shape():
    assert ZatcaScraper._extract_items(_INVALID_VIEW_RESPONSE) == []


def test_extract_items_handles_null_response():
    assert ZatcaScraper._extract_items("null") == []


def test_extract_items_handles_bad_json():
    assert ZatcaScraper._extract_items("not json") == []


def test_parse_last_modified_extracts_real_date():
    assert _parse_last_modified(_LEAF_PAGE_WITH_DATE) == date(2026, 8, 26)


def test_parse_last_modified_returns_none_when_missing():
    assert _parse_last_modified(_LEAF_PAGE_WITHOUT_DATE) is None


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeHttp:
    def __init__(self, api_responses: dict[str, str], leaf_pages: dict[str, str]) -> None:
        self.api_responses = api_responses
        self.leaf_pages = leaf_pages
        self.requested: list[str] = []

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.requested.append(url)
        if "PortalHandler.ashx" in url:
            for category, body in self.api_responses.items():
                if f"/RulesRegulations/{category}/Pages" in url:
                    return _FakeResponse(body)
            return _FakeResponse("null")
        for filename, body in self.leaf_pages.items():
            if url.endswith(filename):
                return _FakeResponse(body)
        return _FakeResponse(_LEAF_PAGE_WITHOUT_DATE)


class _FakeStore:
    def write_raw(self, *args: object, **kwargs: object) -> None:
        return None


def test_build_doc_end_to_end():
    scraper = _scraper()
    scraper.http = _FakeHttp({}, {"ZakatRegulations.aspx": _LEAF_PAGE_WITH_DATE})  # type: ignore[assignment]
    scraper.store = _FakeStore()  # type: ignore[assignment]
    item = ZatcaScraper._extract_items(_TAXES_API_RESPONSE)[0]

    doc = asyncio.run(scraper._build_doc(item, "Taxes"))

    assert doc is not None
    assert doc.title == "The Implementing Regulation for Zakat Collection"
    assert doc.doc_type == DocumentType.TAX_RULING
    assert (
        str(doc.url) == "https://zatca.gov.sa/en/RulesRegulations/Taxes/Pages/ZakatRegulations.aspx"
    )
    assert doc.last_modified == date(2026, 8, 26)
    assert doc.published_gregorian is None  # a page-edit timestamp is not an issuance date
    assert doc.published_hijri is None
    assert doc.verified is True


def test_build_doc_skips_item_without_resolvable_date():
    scraper = _scraper()
    scraper.http = _FakeHttp({}, {"ZakatRegulations.aspx": _LEAF_PAGE_WITHOUT_DATE})  # type: ignore[assignment]
    scraper.store = _FakeStore()  # type: ignore[assignment]
    item = ZatcaScraper._extract_items(_TAXES_API_RESPONSE)[0]

    doc = asyncio.run(scraper._build_doc(item, "Taxes"))

    assert doc is None


def test_discover_maps_categories_to_doc_types_and_respects_max_items():
    agreements_response = """
    [{"LinkFilename": "cyprus-convention.aspx", "Title": "Cyprus Convention", "Visibility": "1",
      "FileLeafRef": "cyprus-convention.aspx", "ID": 3}]
    """
    source = SourceConfig(
        key="zatca_updates",
        name="ZATCA",
        scraper="zatca",
        base_url="https://zatca.gov.sa",
        categories=["tax_ruling"],
        extra={"max_items": 1},
    )
    http = _FakeHttp(
        {"Taxes": _TAXES_API_RESPONSE, "Agreements": agreements_response},
        {
            "ZakatRegulations.aspx": _LEAF_PAGE_WITH_DATE,
            "cyprus-convention.aspx": _LEAF_PAGE_WITH_DATE,
        },
    )
    scraper = ZatcaScraper(source, http, _FakeStore())  # type: ignore[arg-type]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())
    by_title = {d.title: d for d in docs}
    zakat_doc = by_title["The Implementing Regulation for Zakat Collection"]
    assert zakat_doc.doc_type == DocumentType.TAX_RULING
    assert by_title["Cyprus Convention"].doc_type == DocumentType.REGULATION
    assert all(d.verified for d in docs)
