from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType
from saudi_law_tracker.scrapers.umm_al_qura import UmmAlQuraScraper

_ISSUES_ARCHIVE_PAGE = """
<table id="issuesTable">
  <tr><th>رقم العدد</th><th>التاريخ</th><th>الملف</th></tr>
  <tr>
    <td>5182</td>
    <td>1447/03/17 هـ</td>
    <td><a href="/files/gazette/5182.pdf">تحميل</a></td>
  </tr>
  <tr>
    <td>5181</td>
    <td>1447/03/10 هـ</td>
    <td>no link</td>
  </tr>
  <tr>
    <td>only one cell</td>
  </tr>
</table>
"""


def _scraper() -> UmmAlQuraScraper:
    source = SourceConfig(
        key="umm_al_qura",
        name="Umm Al-Qura",
        scraper="umm_al_qura",
        base_url="https://www.uqn.gov.sa",
        start_paths=["/Pages/Issues.aspx"],
        categories=["gazette_issue"],
    )
    return UmmAlQuraScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_header_row_is_skipped():
    row = HTMLParser(_ISSUES_ARCHIVE_PAGE).css("#issuesTable tr")[0]
    assert _scraper()._parse_row(row) is None


def test_parse_row_extracts_issue_number_date_and_pdf():
    row = HTMLParser(_ISSUES_ARCHIVE_PAGE).css("#issuesTable tr")[1]
    doc = _scraper()._parse_row(row)

    assert doc is not None
    assert doc.title == "جريدة أم القرى - العدد 5182"
    assert doc.doc_type == DocumentType.GAZETTE_ISSUE
    assert doc.reference_number == "5182"
    assert doc.published_hijri == "1447-03-17"
    assert doc.published_gregorian == date(2025, 9, 9)
    assert str(doc.url) == "https://www.uqn.gov.sa/files/gazette/5182.pdf"
    assert doc.pdf_urls and str(doc.pdf_urls[0]) == "https://www.uqn.gov.sa/files/gazette/5182.pdf"
    assert doc.verified is True


def test_row_without_pdf_link_is_skipped():
    row = HTMLParser(_ISSUES_ARCHIVE_PAGE).css("#issuesTable tr")[2]
    assert _scraper()._parse_row(row) is None


def test_malformed_row_is_skipped():
    row = HTMLParser(_ISSUES_ARCHIVE_PAGE).css("#issuesTable tr")[3]
    assert _scraper()._parse_row(row) is None
