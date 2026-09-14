# ruff: noqa: E501 -- real captured markup below has some genuinely long
# attribute values (tooltip text); wrapping them would mean editing bytes
# that are supposed to be a faithful copy of the live page.
from __future__ import annotations

import asyncio
from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.citc import CitcScraper

# Trimmed copies of the actual saved snapshots in data/raw/citc/ (first two
# rows of each section, from the 2026-09-14 13:59 run):
#   20260914T135933Z__documents.html
#   20260914T135934Z__decisions.html
#   20260914T135937Z__consultations.html
# against mutasilbus.cst.gov.sa/regulations/{documents,decisions,consultations}/
# (NOT www.cst.gov.sa, which redirects into an unrelated SPA with no
# regulations content, and has no __NEXT_DATA__ blob at all). The only
# changes from the saved bytes: `&#xHHHH;` numeric character references
# decoded to plain Unicode, and the template's blank lines between tags
# collapsed -- both meaning-preserving (selectolax parses either form
# identically), not a content change.

_DOCUMENTS_PAGE = """
<table class="table table-reg"><tbody>
<tr data-href="/regulations/documents/details?id=E9jCkJAP%2FePMz8LB8ZzV4Q%3D%3D">
    <td>
        <div class="fw-bold mb-1 fs-16 reg-table-title" data-bs-toggle="tooltip" title="تنظيمات تحديد وتصنيف الأسواق والسيطرة في قطاع الاتصالات">تنظيمات تحديد وتصنيف الأسواق والسيطرة في قطاع...</div>
        <p class="truncate-2 mb-0 reg-table-title">
            <span class="fw-bold text-secondary me-1">الوصف:</span>
            <span data-bs-toggle="tooltip" title="تغطي هذه التنظيمات المتطلبات التنظيمية المسبقة للحد من الممارسات غير التنافسية المطبقة على مقدمي الخدمات المسيطرين، سواء كانوا يتمتعون بالسيطرة على السوق أو القدرة على ممارسة قوة سوقية كبرى. كما تحدد هذه التنظيمات آلية تطبيق المتطلبات التنظيمية المسبقة للحد من ممارسات السيطرة قبل وقوعها، ولا تتناول هذه التنظيمات التعامل مع ممارسات السيطرة بعد وقوعها.">
                تغطي هذه التنظيمات المتطلبات التنظيمية المسبقة...
            </span>
        </p>
    </td>
    <td>REGULATIONSG58</td>
    <td>عام</td>
    <td>3-197-2025</td>
    <td>25/12/2025</td>
    <td>تنظيمات</td>
    <td>عام</td>
</tr>
<tr data-href="/regulations/documents/details?id=CRFWI34ouXB%2BLy5hcb%2FqJA%3D%3D">
    <td>
        <div class="fw-bold mb-1 fs-16 reg-table-title" data-bs-toggle="tooltip" title="العرض المرجعي لشركة الاتصالات السعودية STC  الوثيقة الأساسية">العرض المرجعي لشركة الاتصالات السعودية STC ...</div>
        <p class="truncate-2 mb-0 reg-table-title">
            <span class="fw-bold text-secondary me-1">الوصف:</span>
            <span data-bs-toggle="tooltip" title="العرض المرجعي هو مستند منشور وفقًا لتنظيمات ربط الاتصال البيني وتنظيمات الوصول إلى المرافق المادية تحدد مجموعة قياسية من الأمور الفنية والتجارية التي من خلالها يقدم مقدم الخدمة المسيطر خدمات الربط البيني والوصول النفاذ إلى أي مشغل مرخص آخر يطلبه.">
                العرض المرجعي هو مستند منشور وفقًا لتنظيمات ربط...
            </span>
        </p>
    </td>
    <td>OTHERM12</td>
    <td>عام</td>
    <td>564/1447</td>
    <td>03/12/2025</td>
    <td>أخرى</td>
    <td>السوق</td>
</tr>
</tbody></table>
"""

_DECISIONS_PAGE = """
<table class="table table-reg"><tbody>
<tr data-href="/regulations/decisions/details?id=ZLYmozIrSEcx1NgN9uwKyw%3D%3D">
    <td>584/1448</td>
    <td>
        <p class="truncate-2 mb-0 reg-table-title" data-bs-toggle="tooltip" title="تصنف شركة الاتصالات السعودية مقدم خدمة مسيطر في سوق خدمات النفاذ وإنشاء المكالمات على شبكة الاتصالات المتنقلة بالجملة">
            تصنف شركة الاتصالات السعودية مقدم خدمة مسيطر في...
        </p>
    </td>
    <td data-bs-toggle="tooltip" title="التاريخ الميلادي: 25/06/2026">10/01/1448</td>
    <td data-bs-toggle="tooltip" title="التاريخ الميلادي: 20/09/2026">09/04/1448</td>
    <td>عام</td>
</tr>
<tr data-href="/regulations/decisions/details?id=Lvthp%2BX8pi6qu0XE1iILNg%3D%3D">
    <td>583/1448</td>
    <td>
        <p class="truncate-2 mb-0 reg-table-title" data-bs-toggle="tooltip" title="تصنف شركة الاتصالات السعودية مقدم خدمة مسيطر في سوق خدمات وصلات دوائر الترنك للخطوط المؤجرة بالجملة">
            تصنف شركة الاتصالات السعودية مقدم خدمة مسيطر في...
        </p>
    </td>
    <td data-bs-toggle="tooltip" title="التاريخ الميلادي: 25/06/2026">10/01/1448</td>
    <td data-bs-toggle="tooltip" title="التاريخ الميلادي: 20/09/2026">09/04/1448</td>
    <td>عام</td>
</tr>
</tbody></table>
"""

_CONSULTATIONS_PAGE = """
<table class="table table-reg"><tbody>
<tr data-href="/regulations/consultations/details?id=2wkzWmKu2%2FIZMybCts0CHA%3D%3D">
    <td>
        <div class="reg-table-title">
            تنظيمات وإرشادات قطاع الفضاء
        </div>
    </td>
    <td>17/1447</td>
    <td>
        <span class="bill_status_circle bill_status_circle_dark bg-gray-light me-1"></span>
        <span>منتهية</span>
    </td>
    <td><span data-bs-toggle="tooltip" title="تاريخ البداية هجري: 04/07/1447">24/12/2025</span></td>
    <td><span data-bs-toggle="tooltip" title="تاريخ النهاية هجري: 05/10/1447">24/03/2026</span></td>
</tr>
<tr data-href="/regulations/consultations/details?id=K4zNlCdBlgM%2FRwTE%2B6XhaQ%3D%3D">
    <td>
        <div class="reg-table-title">
            الخطة الوطنية للطيف الترددي
        </div>
    </td>
    <td>1/1447</td>
    <td>
        <span class="bill_status_circle bill_status_circle_dark bg-gray-light me-1"></span>
        <span>منتهية</span>
    </td>
    <td><span data-bs-toggle="tooltip" title="تاريخ البداية هجري: 09/07/1447">29/12/2025</span></td>
    <td><span data-bs-toggle="tooltip" title="تاريخ النهاية هجري: 20/08/1447">08/02/2026</span></td>
</tr>
</tbody></table>
"""

_NO_TABLE_PAGE = "<html><body>digital-stamp-card widget only, no regulations table</body></html>"


def _scraper(start_paths: list[str]) -> CitcScraper:
    source = SourceConfig(
        key="citc",
        name="CST",
        scraper="citc",
        base_url="https://mutasilbus.cst.gov.sa",
        start_paths=start_paths,
        categories=["regulation", "public_consultation"],
    )
    return CitcScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_extract_rows_reads_real_documents_table():
    rows = CitcScraper._extract_rows(_DOCUMENTS_PAGE)
    assert len(rows) == 2


def test_extract_rows_returns_empty_list_without_reg_table():
    assert CitcScraper._extract_rows(_NO_TABLE_PAGE) == []


def test_parse_row_documents_uses_title_attribute_and_gregorian_column():
    rows = CitcScraper._extract_rows(_DOCUMENTS_PAGE)
    doc = _scraper(["/regulations/documents/"])._parse_row(rows[0], "documents")

    assert doc is not None
    assert doc.title == "تنظيمات تحديد وتصنيف الأسواق والسيطرة في قطاع الاتصالات"
    assert doc.doc_type == DocumentType.REGULATION
    assert doc.reference_number == "REGULATIONSG58"
    assert doc.published_hijri is None
    assert doc.published_gregorian == date(2025, 12, 25)
    assert str(doc.url) == (
        "https://mutasilbus.cst.gov.sa/regulations/documents/details"
        "?id=E9jCkJAP%2FePMz8LB8ZzV4Q%3D%3D"
    )
    assert doc.verified is True
    assert "documents" in doc.categories


def test_parse_row_decisions_merges_hijri_text_and_gregorian_tooltip():
    rows = CitcScraper._extract_rows(_DECISIONS_PAGE)
    doc = _scraper(["/regulations/decisions/"])._parse_row(rows[0], "decisions")

    assert doc is not None
    assert doc.reference_number == "584/1448"
    assert doc.published_hijri == "1448-01-10"
    assert doc.published_gregorian == date(2026, 6, 25)  # from the tooltip, not converted


def test_parse_row_consultations_merges_gregorian_text_and_hijri_tooltip():
    rows = CitcScraper._extract_rows(_CONSULTATIONS_PAGE)
    doc = _scraper(["/regulations/consultations/"])._parse_row(rows[0], "consultations")

    assert doc is not None
    assert doc.doc_type == DocumentType.PUBLIC_CONSULTATION
    assert doc.reference_number == "17/1447"
    assert doc.published_hijri == "1447-07-04"
    assert doc.published_gregorian == date(2025, 12, 24)  # from the visible text, not the tooltip


def test_parse_row_without_title_is_skipped():
    rows = CitcScraper._extract_rows(_DOCUMENTS_PAGE)
    row = rows[0]
    for node in row.css(".reg-table-title"):
        node.decompose()
    assert _scraper(["/regulations/documents/"])._parse_row(row, "documents") is None


def test_discover_walks_all_three_sections_and_tags_each():
    class _FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    class _FakeHttp:
        def __init__(self, pages: dict[str, str]) -> None:
            self.pages = pages
            self.requested: list[str] = []

        async def get(self, url: str, **kwargs: object) -> _FakeResponse:
            self.requested.append(url)
            for section, text in self.pages.items():
                if section in url:
                    return _FakeResponse(text)
            return _FakeResponse("")

    class _FakeStore:
        def write_raw(self, *args: object, **kwargs: object) -> None:
            return None

    http = _FakeHttp(
        {
            "documents": _DOCUMENTS_PAGE,
            "decisions": _DECISIONS_PAGE,
            "consultations": _CONSULTATIONS_PAGE,
        }
    )
    scraper = _scraper(
        [
            "/regulations/documents/",
            "/regulations/decisions/",
            "/regulations/consultations/",
        ]
    )
    scraper.http = http  # type: ignore[assignment]
    scraper.store = _FakeStore()  # type: ignore[assignment]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())

    assert len(docs) == 6  # 2 rows x 3 sections
    assert len(http.requested) == 3
    sections_seen = {doc.categories[-1] for doc in docs}
    assert sections_seen == {"documents", "decisions", "consultations"}
