"""Bureau of Experts at the Council of Ministers — laws.boe.gov.sa

The Arabic portal paths (``/ar/Regulations``, ``/ar/BoeLaws/Laws``) 500 as of
2026. The working listing is the search endpoint, which supports newest-first
sorting and simple page-number pagination::

    /BoeLaws/Laws/Search?PageNumber=<n>&SortDirection=DES

Each result row is ``div.search_result_item``::

    a.result-keyword-title   title + href /BoeLaws/Laws/LawDetails/<guid>/1
    p.result-keyword-desc    one-line summary
    span "تاريخ الإصدار: <hijri> هـ"   issue date  -> published_hijri/-_gregorian
    span "تاريخ النشر:  <hijri> هـ"    gazette publication date -> effective_date

Dates are Hijri in year/month/day order. The royal-decree / ministerial
-resolution reference number only appears on the detail page.

TODO(selectors): follow LawDetails to pick up the reference number and the
full-text / PDF links.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper, register

_DEFAULT_MAX_PAGES = 3
_SEARCH_QUERY = "PageNumber={page}&SortDirection=DES"


def _doc_type(title: str) -> DocumentType:
    if title.startswith("لائحة"):
        return DocumentType.REGULATION
    if title.startswith(("نظام", "النظام")):
        return DocumentType.LAW
    return DocumentType.OTHER


@register("bureau_of_experts")
class BureauOfExpertsScraper(BaseScraper):
    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        max_pages = int(self.source.extra.get("max_pages", _DEFAULT_MAX_PAGES))
        for base in self.source.start_paths:
            for page in range(1, max_pages + 1):
                sep = "&" if "?" in base else "?"
                url = self.abs_url(f"{base}{sep}{_SEARCH_QUERY.format(page=page)}")
                resp = await self.http.get(url)
                self.store.write_raw(self.source.key, f"search_p{page}", resp.text)

                rows = HTMLParser(resp.text).css("div.search_result_item")
                if not rows:
                    break
                for row in rows:
                    doc = self._parse_row(row)
                    if doc is not None:
                        yield doc

    def _parse_row(self, row: Node) -> RegulatoryDocument | None:
        link = row.css_first("a.result-keyword-title")
        if link is None:
            return None
        title = clean(link.text())
        href = link.attributes.get("href") or ""
        if not title or not href:
            return None

        desc_node = row.css_first("p.result-keyword-desc")
        summary = clean(desc_node.text()) if desc_node else None

        issue_hijri = None
        issue_greg = pub_greg = None
        for span in row.css("span"):
            text = clean(span.text())
            if "الإصدار" in text:
                issue_hijri, issue_greg = parse_hijri_date(text)
            elif "النشر" in text:
                _, pub_greg = parse_hijri_date(text)

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=_doc_type(title),
            url=self.abs_url(href),
            summary=summary,
            published_hijri=issue_hijri,
            published_gregorian=issue_greg,
            effective_date=pub_greg,
            categories=self.source.categories,
        )
