# ruff: noqa: E501 -- real captured markup below has some genuinely long
# lines (deeply nested Drupal field-wrapper divs, percent-encoded hrefs);
# wrapping them would mean editing bytes that are supposed to be a faithful
# copy of the live page.
from __future__ import annotations

import asyncio
from datetime import date

from saudi_law_tracker.config import SourceConfig
from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.scrapers.mhrsd import MhrsdScraper

# Trimmed copies of the actual saved snapshots in data/raw/mhrsd_labor/
# (first two rows of each section, from the 2026-09-14 13:59 run):
#   20260914T135934Z__ministerial-decisions.html
#   20260914T135936Z__procedure.html
#   20260914T135938Z__news.html
# against www.hrsd.gov.sa. `.policy-card`/`.news-card` (the previous
# config's selectors) don't exist anywhere on the site; these are the real
# Drupal Views listings, identical in structure across all three real
# start_paths (see mhrsd.py's docstring). The only changes from the saved
# bytes: the news rows' `.field--name-field-media` image/`<picture>` block
# (several KB of `srcSet` noise, parsed by nothing) removed as a whole,
# well-formed subtree, and the template's blank lines between tags
# collapsed -- neither changes what any selector in mhrsd.py sees.

_DECISIONS_PAGE = """
<div class="view-content row">
<div class="views-row col-lg-4 col-md-6 col-12 mb-4">
<div class="card has-shadow is-white">
<div class="card-content medium-title">
<div id="_R_5a3anll5dd9al8ql9bsnj9lb_">
<div class="field-wrapper">
<div class="field field--name-node-title field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<h2 class="text-lg text-semibold">
  <a href="/knowledge-centre/decisions-and-regulations/ministerial-decisions/145268" hreflang="ar">قرار تحديث بيانات ومواقع  المنشآت 145268</a>
</h2>
</div>
</div>
</div>
</div>
<div class="field-wrapper">
<div class="field field--name-body field--type-text-with-summary field--label-hidden field-formatter--smart_trim field__item">
<div>
<p>انطلاقًا من حرص الوزارة على ضمان وجود قاعدة بيانات دقيقة ومحدثة، مما يساهم في تعزيز الشفافية وتسهيل عمليات الرقابة، وضمان الالتزام باللوائح والأنظمة...</p>
</div>
</div>
</div>
</div>
<div class="card-date">
<div class="field-wrapper field--has-icon">
<i class="icon-field icon-field-created icon-date-dots text-sa-flag-600">
</i>
<div class="field field--name-created field--type-created field--label-hidden field-formatter--hijri_dual_date_formatter field__item">
<div class="hijri-dual-date-formatter">
<span class="hijri-date">27-شوال-1445</span>
<span class="date-separator">-</span>
<span class="gregorian-date">06-مايو-2024</span>
</div>
</div>
</div>
</div>
<div class="card-tags">
<div class="field-wrapper">
<div class="field field--name-field-sector field--type-entity-reference field--label-hidden field-formatter--entity_reference_labels field__items">
<div class="field__item">
<div>
<div class="tag-md tag-neutral-50">قطاع العمل</div>
</div>
</div>
</div>
</div>
</div>
<div class="card-actions justify-content-end ">
<div class="field-wrapper">
<div class="field field--name-saud-read-more field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<a href="/knowledge-centre/decisions-and-regulations/ministerial-decisions/145268" class="btn-lg btn-neutral-100 btn-arrow reversed-icon" aria-label="قرار تحديث بيانات ومواقع  المنشآت 145268" hreflang="ar">
</a>
</div>
</div>
</div>
</div>
</div>
</div>
<div class="views-row col-lg-4 col-md-6 col-12 mb-4">
<div class="card has-shadow is-white">
<div class="card-content medium-title">
<div id="_R_5a5anll5dd9al8ql9bsnj9lb_">
<div class="field-wrapper">
<div class="field field--name-node-title field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<h2 class="text-lg text-semibold">
  <a href="/knowledge-centre/decisions-and-regulations/ministerial-decisions/05012024" hreflang="ar">قرار اعتماد القواعد والإجراءات المنظمة للتسوية الودية في الخلافات العمالية </a>
</h2>
</div>
</div>
</div>
</div>
<div class="field-wrapper">
<div class="field field--name-body field--type-text-with-summary field--label-hidden field-formatter--smart_trim field__item">
<div>
<p>قرار وزاري باعتماد القواعد والإجراءات المنظمة للتسوية الودية في الخلافات العمالية بالصيغة المرافقة للقرار. ‏قرار رقم ٩١٢٨٥ وتاريخ ٢٠-٠٦-١٤٤٥ه‍.</p>
</div>
</div>
</div>
</div>
<div class="card-date">
<div class="field-wrapper field--has-icon">
<i class="icon-field icon-field-created icon-date-dots text-sa-flag-600">
</i>
<div class="field field--name-created field--type-created field--label-hidden field-formatter--hijri_dual_date_formatter field__item">
<div class="hijri-dual-date-formatter">
<span class="hijri-date">22-جمادى الآخرة-1445</span>
<span class="date-separator">-</span>
<span class="gregorian-date">04-يناير-2024</span>
</div>
</div>
</div>
</div>
<div class="card-tags">
<div class="field-wrapper">
<div class="field field--name-field-sector field--type-entity-reference field--label-hidden field-formatter--entity_reference_labels field__items">
<div class="field__item">
<div>
<div class="tag-md tag-neutral-50">قطاع العمل</div>
</div>
</div>
</div>
</div>
</div>
<div class="card-actions justify-content-end ">
<div class="field-wrapper">
<div class="field field--name-saud-read-more field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<a href="/knowledge-centre/decisions-and-regulations/ministerial-decisions/05012024" class="btn-lg btn-neutral-100 btn-arrow reversed-icon" aria-label="قرار اعتماد القواعد والإجراءات المنظمة للتسوية الودية في الخلافات العمالية " hreflang="ar">
</a>
</div>
</div>
</div>
</div>
</div>
</div>
</div>
"""

_PROCEDURE_PAGE = """
<div class="view-content row">
<div class="views-row col-sm-12 col-md-6  col-lg-4 mb-4">
<div class="card has-shadow is-white">
<div class="card-content ">
<div id="_R_ak6lfbaald9al8ql9bsnj9lb_">
<div class="field-wrapper">
<div class="field field--name-node-title field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<h2 class="text-lg text-semibold">
  <a href="/knowledge-centre/decisions-and-regulations/regulation-and-procedures/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D8%B9%D8%AF-%D9%88%D8%A7%D9%84%D8%A5%D8%AC%D8%B1%D8%A7%D8%A1%D8%A7%D8%AA-%D8%A7%D9%84%D9%85%D9%86%D8%B8%D9%85%D8%A9-%D9%84%D8%AA%D8%B3%D9%88%D9%8A%D8%A9-%D8%AE%D9%84%D8%A7%D9%81%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D8%A7%D9%84%D8%A9" hreflang="ar">القواعد والإجراءات المنظمة لتسوية خلافات العمالة المنزلية ومن في حكمهم</a>
</h2>
</div>
</div>
</div>
</div>
<div class="field-wrapper">
<div class="field field--name-body field--type-text-with-summary field--label-hidden field-formatter--smart_trim field__item">
<div>
<p>هذه القواعد تتعلق بـ تنظيم إجراءات التسوية الودية لمنازعات العمالة المنزلية ومن في حكمهم في وزارة الموارد البشرية والتنمية الاجتماعية، وتهدف إلى حل</p>
</div>
</div>
</div>
</div>
<div class="card-date">
<div class="field-wrapper field--has-icon">
<i class="icon-field icon-field-created icon-date-dots text-sa-flag-600">
</i>
<div class="field field--name-created field--type-created field--label-hidden field-formatter--hijri_dual_date_formatter field__item">
<div class="hijri-dual-date-formatter">
<span class="hijri-date">27-ذو القعدة-1447</span>
<span class="date-separator">-</span>
<span class="gregorian-date">14-مايو-2026</span>
</div>
</div>
</div>
</div>
<div class="card-tags">
<div class="field-wrapper">
<div class="field field--name-field-target field--type-entity-reference field--label-hidden field-formatter--entity_reference_labels field__items">
<div class="field__item">
<div>
<div class="tag-md tag-primary-600">أصحاب عمل</div>
</div>
</div>
<div class="field__item">
<div>
<div class="tag-md tag-primary-600">أفراد</div>
</div>
</div>
</div>
</div>
<div class="field-wrapper">
<div class="field field--name-field-sector field--type-entity-reference field--label-hidden field-formatter--entity_reference_labels field__items">
<div class="field__item">
<div>
<div class="tag-md tag-neutral-50">قطاع العمل</div>
</div>
</div>
</div>
</div>
</div>
<div class="card-actions justify-content-end ">
<div class="field-wrapper">
<div class="field field--name-saud-read-more field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<a href="/knowledge-centre/decisions-and-regulations/regulation-and-procedures/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D8%B9%D8%AF-%D9%88%D8%A7%D9%84%D8%A5%D8%AC%D8%B1%D8%A7%D8%A1%D8%A7%D8%AA-%D8%A7%D9%84%D9%85%D9%86%D8%B8%D9%85%D8%A9-%D9%84%D8%AA%D8%B3%D9%88%D9%8A%D8%A9-%D8%AE%D9%84%D8%A7%D9%81%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D8%A7%D9%84%D8%A9" class="btn-lg btn-neutral-100 btn-arrow reversed-icon" aria-label="القواعد والإجراءات المنظمة لتسوية خلافات العمالة المنزلية ومن في حكمهم" hreflang="ar">
</a>
</div>
</div>
</div>
</div>
</div>
</div>
</div>
"""

_NEWS_PAGE = """
<div class="view-content">
<div class="views-row col-xl-3 col-lg-4 col-md-6 col-sm-12 mb-4">
<div class="card has-shadow is-white">
<div class="card-header">
<div class="field-wrapper">
</div>
</div>
<div class="card-content ">
<div id="_R_5a3anll5dd9al8ql9bsnj9lb_">
<div class="field-wrapper">
<div class="field field--name-node-title field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<h2 class="text-lg text-semibold">
  <a href="/media-center/news/%D8%A3%D8%B9%D9%85%D8%A7%D9%84-%D8%A7%D9%84%D8%AF%D9%88%D8%B1%D8%A9-%D8%A7%D9%84%D9%8052-%D9%84%D9%85%D8%A4%D8%AA%D9%85%D8%B1-%D8%A7%D9%84%D8%B9%D9%85%D9%84-%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A-%D8%A8%D8%A7%D9%84%D9%82%D8%A7%D9%87%D8%B1%D8%A9" hreflang="ar">نائب وزير الموارد البشرية والتنمية الاجتماعية للعمل يرأس وفد المملكة المشارك في أعمال الدورة الـ52 لمؤتمر العمل العربي بالقاهرة</a>
</h2>
</div>
</div>
</div>
</div>
<div class="card-date">
<div class="field-wrapper field--has-icon">
<i class="icon-field icon-field-created icon-date-dots text-sa-flag-600">
</i>
<div class="field field--name-created field--type-created field--label-hidden field-formatter--hijri_dual_date_formatter field__item">
<div class="hijri-dual-date-formatter">
<span class="hijri-date">02-ربيع الآخر-1448</span>
<span class="date-separator">-</span>
<span class="gregorian-date">13-سبتمبر-2026</span>
</div>
</div>
</div>
</div>
<div class="card-tags">
<div class="field-wrapper">
<div class="field field--name-field-target field--type-entity-reference field--label-visually_hidden field-formatter--entity_reference_labels">
<div class="field__label visually-hidden">الفئة المستهدفة</div>
<div class="field__items">
<div class="field__item">
<div>
<div class="tag-md tag-primary-600">حقوق العمالة في المملكة العربية السعودية</div>
</div>
</div>
<div class="field__item">
<div>
<div class="tag-md tag-primary-600">نظام العمل في المملكة العربية السعودية</div>
</div>
</div>
</div>
</div>
</div>
<div class="field-wrapper">
<div class="field field--name-field-sector field--type-entity-reference field--label-hidden field-formatter--entity_reference_labels field__items">
<div class="field__item">
<div>
<div class="tag-md tag-neutral-50">قطاع العمل</div>
</div>
</div>
</div>
</div>
</div>
<div class="card-actions justify-content-end ">
<div class="field-wrapper">
<div class="field field--name-saud-read-more field--type-ds field--label-hidden field-formatter--ds_field field__item">
<div>
<a href="/media-center/news/%D8%A3%D8%B9%D9%85%D8%A7%D9%84-%D8%A7%D9%84%D8%AF%D9%88%D8%B1%D8%A9-%D8%A7%D9%84%D9%8052-%D9%84%D9%85%D8%A4%D8%AA%D9%85%D8%B1-%D8%A7%D9%84%D8%B9%D9%85%D9%84-%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A-%D8%A8%D8%A7%D9%84%D9%82%D8%A7%D9%87%D8%B1%D8%A9" class="btn-lg btn-neutral-100 btn-arrow reversed-icon" aria-label="نائب وزير الموارد البشرية والتنمية الاجتماعية للعمل يرأس وفد المملكة المشارك في أعمال الدورة الـ52 لمؤتمر العمل العربي بالقاهرة" hreflang="ar">
</a>
</div>
</div>
</div>
</div>
</div>
</div>
</div>
</div>
"""

_NO_VIEW_CONTENT_PAGE = "<html><body>seeds-ui-grid-item widget only, no dated listing</body></html>"


def _scraper(start_paths: list[str]) -> MhrsdScraper:
    source = SourceConfig(
        key="mhrsd_labor",
        name="MHRSD",
        scraper="mhrsd",
        base_url="https://www.hrsd.gov.sa",
        start_paths=start_paths,
        categories=["ministerial_decision", "regulation", "labor_law_amendment"],
    )
    return MhrsdScraper(source, http=None, store=None)  # type: ignore[arg-type]


def test_extract_rows_reads_real_views_row_listing():
    rows = MhrsdScraper._extract_rows(_DECISIONS_PAGE)
    assert len(rows) == 2


def test_extract_rows_returns_empty_list_without_view_content():
    assert MhrsdScraper._extract_rows(_NO_VIEW_CONTENT_PAGE) == []


def test_parse_row_ministerial_decision_reads_title_dates_and_numeric_ref():
    rows = MhrsdScraper._extract_rows(_DECISIONS_PAGE)
    doc = _scraper(
        ["/knowledge-centre/decisions-and-regulations/ministerial-decisions"]
    )._parse_row(rows[0], "ministerial-decisions")

    assert doc is not None
    assert doc.title == "قرار تحديث بيانات ومواقع المنشآت 145268"
    assert doc.doc_type == DocumentType.MINISTERIAL_DECISION
    assert doc.reference_number == "145268"  # numeric URL slug, not percent-encoded
    assert doc.published_hijri == "1445-10-27"
    assert doc.published_gregorian == date(2024, 5, 6)  # from the site's own Gregorian span
    assert doc.summary is not None and doc.summary.startswith("انطلاقًا")
    assert doc.verified is True
    assert "ministerial-decisions" in doc.categories


def test_parse_row_procedure_drops_percent_encoded_slug_as_reference():
    rows = MhrsdScraper._extract_rows(_PROCEDURE_PAGE)
    doc = _scraper(
        ["/knowledge-centre/decisions-and-regulations/regulation-and-procedures/procedure"]
    )._parse_row(rows[0], "procedure")

    assert doc is not None
    assert doc.doc_type == DocumentType.REGULATION
    assert doc.reference_number is None  # slug is the percent-encoded title, not a real id
    assert doc.published_hijri == "1447-11-27"
    assert doc.published_gregorian == date(2026, 5, 14)


def test_parse_row_news_gets_news_doc_type_and_no_summary():
    rows = MhrsdScraper._extract_rows(_NEWS_PAGE)
    doc = _scraper(["/media-center/news"])._parse_row(rows[0], "news")

    assert doc is not None
    assert doc.doc_type == DocumentType.NEWS
    assert doc.summary is None  # news cards carry no .field--name-body
    assert doc.published_hijri == "1448-04-02"
    assert doc.published_gregorian == date(2026, 9, 13)


def test_parse_row_without_title_link_is_skipped():
    rows = MhrsdScraper._extract_rows(_DECISIONS_PAGE)
    row = rows[0]
    link = row.css_first(".field--name-node-title a")
    assert link is not None
    link.decompose()
    assert (
        _scraper(["/knowledge-centre/decisions-and-regulations/ministerial-decisions"])._parse_row(
            row, "ministerial-decisions"
        )
        is None
    )


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


def test_discover_walks_all_three_sections_and_tags_each():
    http = _FakeHttp(
        {
            "ministerial-decisions": _DECISIONS_PAGE,
            "procedure": _PROCEDURE_PAGE,
            "news": _NEWS_PAGE,
        }
    )
    scraper = _scraper(
        [
            "/knowledge-centre/decisions-and-regulations/ministerial-decisions",
            "/knowledge-centre/decisions-and-regulations/regulation-and-procedures/procedure",
            "/media-center/news",
        ]
    )
    scraper.http = http  # type: ignore[assignment]
    scraper.store = _FakeStore()  # type: ignore[assignment]

    async def collect() -> list[RegulatoryDocument]:
        return [doc async for doc in scraper.discover()]

    docs = asyncio.run(collect())

    assert len(docs) == 4  # 2 decisions + 1 procedure + 1 news
    assert len(http.requested) == 3
    sections_seen = {doc.categories[-1] for doc in docs}
    assert sections_seen == {"ministerial-decisions", "procedure", "news"}
