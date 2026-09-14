"""Ministry of Human Resources & Social Development — hrsd.gov.sa

Confirmed live 2026-09-14: neither `.policy-card` nor `.news-card` (the
previous config's selectors) exist anywhere on the site, and the old
`start_paths` don't resolve to real content --
`/ar/policies` redirects (301, then 308) to a generic "website policies"
page (privacy policy, terms of use -- nothing about labor law), and
`/ar/media-center/ministry-news` 404s outright.

The site *is* Drupal underneath a Next.js frontend, and `field__item` really
is everywhere, exactly as flagged -- it's the class Drupal's Field API puts
on every rendered field, so it shows up on every widget on the site rather
than pinning down one listing. The generic content-card grid
(`seeds-ui-grid-item`) that pattern belongs to is a static menu of category
tiles (e.g. "Regulations and Procedures" -> "Evidence" / "Procedures"), not
itself a list of dated documents.

The actual dated listings -- the ones this scraper wants -- are Drupal
Views, rendered as `.view-content .views-row` cards, confirmed live and
identical in structure across all three real `start_paths` below:

  /knowledge-centre/decisions-and-regulations/ministerial-decisions
  /knowledge-centre/decisions-and-regulations/regulation-and-procedures/procedure
  /media-center/news

Each `.views-row` card has a `.field--name-node-title h2 a[href]` (title +
detail link) and a `.hijri-dual-date-formatter` block with separate
`.hijri-date`/`.gregorian-date` spans, each `"DD-<Arabic month name>-YYYY"`
(e.g. `27-شوال-1445` / `06-مايو-2024`) -- both calendars given directly by
the site, so no Hijri<->Gregorian conversion is needed, just Arabic month
name lookup (`_HIJRI_MONTHS`/`_GREGORIAN_MONTHS` below). Ministerial-decision
and procedure cards also carry `.field--name-body p` (used as `summary`).

TODO(coverage): `/regulation-and-procedures/evidence` (the grid's other
tile) wasn't checked -- confirm it's the same Views pattern before adding it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.text import clean
from .base import BaseScraper, register

_GREGORIAN_MONTHS: dict[str, int] = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "أغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}  # fmt: skip

_HIJRI_MONTHS: dict[str, int] = {
    "محرم": 1, "صفر": 2, "ربيع الأول": 3, "ربيع الآخر": 4, "ربيع الثاني": 4,
    "جمادى الأولى": 5, "جمادى الأول": 5, "جمادى الآخرة": 6, "جمادى الثانية": 6,
    "رجب": 7, "شعبان": 8, "رمضان": 9, "شوال": 10, "ذو القعدة": 11, "ذو الحجة": 12,
}  # fmt: skip

_DOC_TYPES: dict[str, DocumentType] = {
    "ministerial-decisions": DocumentType.MINISTERIAL_DECISION,
    "procedure": DocumentType.REGULATION,
    "news": DocumentType.NEWS,
}


def _section_from_path(path: str) -> str | None:
    for section in _DOC_TYPES:
        if section in path:
            return section
    return None


def _parse_ar_date(text: str, months: dict[str, int]) -> tuple[int, int, int] | None:
    """`"DD-<Arabic month name>-YYYY"` -> `(year, month, day)`, or None if the
    text doesn't match (a missing span, an unrecognized month spelling)."""

    parts = clean(text).split("-")
    if len(parts) != 3:
        return None
    day_text, month_name, year_text = parts
    month = months.get(month_name.strip())
    if month is None:
        return None
    try:
        return int(year_text), month, int(day_text)
    except ValueError:
        return None


def _row_dates(row: Node) -> tuple[str | None, date | None]:
    """The Hijri and Gregorian spans are two independent renderings of the
    same underlying date -- both given directly by the site, not derived
    from each other."""

    hijri_str: str | None = None
    hijri_span = row.css_first(".hijri-date")
    if hijri_span is not None:
        parsed = _parse_ar_date(hijri_span.text(), _HIJRI_MONTHS)
        if parsed is not None:
            year, month, day = parsed
            hijri_str = f"{year:04d}-{month:02d}-{day:02d}"

    greg_date: date | None = None
    greg_span = row.css_first(".gregorian-date")
    if greg_span is not None:
        parsed = _parse_ar_date(greg_span.text(), _GREGORIAN_MONTHS)
        if parsed is not None:
            year, month, day = parsed
            try:
                greg_date = date(year, month, day)
            except ValueError:
                greg_date = None

    return hijri_str, greg_date


def _reference_from_url(url: str) -> str | None:
    """The last URL path segment is the node's slug: a short real id for
    ministerial decisions (`145268`, `05012024`), but the percent-encoded
    Arabic title itself for procedure/news nodes (a `%` gives this away) --
    only the former is worth surfacing as a reference number."""

    tail = url.rstrip("/").rsplit("/", 1)[-1]
    if not tail or "%" in tail:
        return None
    return tail


@register("mhrsd")
class MhrsdScraper(BaseScraper):
    tuned = True

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            section = _section_from_path(path)
            if section is None:
                self.log.warning("mhrsd.unknown_section", path=path)
                continue

            url = self.abs_url(path)
            resp = await self.http.get(url)
            self.store.write_raw(self.source.key, section, resp.text)

            for row in self._extract_rows(resp.text):
                doc = self._parse_row(row, section)
                if doc is not None:
                    yield doc

    @staticmethod
    def _extract_rows(html: str) -> list[Node]:
        tree = HTMLParser(html)
        content = tree.css_first(".view-content")
        if content is None:
            return []
        return content.css(".views-row")

    def _parse_row(self, row: Node, section: str) -> RegulatoryDocument | None:
        link = row.css_first(".field--name-node-title a[href]")
        if link is None:
            return None
        title = clean(link.text())
        href = link.attributes.get("href") or ""
        if not title or not href:
            return None

        url = self.abs_url(href)
        hijri, greg = _row_dates(row)

        summary_node = row.css_first(".field--name-body p")
        summary = clean(summary_node.text()) if summary_node is not None else None

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=_DOC_TYPES[section],
            url=url,
            reference_number=_reference_from_url(str(url)),
            summary=summary,
            published_hijri=hijri,
            published_gregorian=greg,
            categories=[*self.source.categories, section],
            verified=True,
        )
