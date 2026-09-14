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

Dates are Hijri in year/month/day order.

The royal-decree / ministerial-resolution reference number and the full-text
PDF only appear on each law's own LawDetails page (``span`` next to it isn't
enough). Confirmed live 2026-09-14 against real LawDetails pages:
`table.table-details` occurs zero times anywhere on the site, and no link
anywhere ends in `.pdf` (the site has no literal `.pdf` URLs at all — file
delivery is entirely through app routes, not static file paths). The real
markup is::

    h4.center             one Arabic sentence giving the promulgating
                           instrument, e.g. "مرسوم ملكي رقم (م/237) وتاريخ
                           1447/11/3هـ" or, just as often, without parens
                           and with "ب" instead of "و": "مرسوم ملكي رقم
                           م/51 بتاريخ 23 / 8 / 1426" -- `_REFERENCE_RE`
                           extracts the number from whichever the first
                           matching heading's *text* actually says, not
                           from a fixed table cell. A page can have more
                           than one (e.g. a Royal Decree heading followed
                           by the Council of Ministers resolution it
                           approves); the first one is this document's own.

    a[href*="/Files/Download/"]   the real, direct PDF link (confirmed live:
                           200, Content-Type: application/pdf) -- labeled
                           "Translated document" in the UI, but it's the
                           only literally-downloadable file on the page.
                           `a[href*="/BoeLaws/Laws/Viewer/"]` links (labeled
                           "اصل الوثيقة") look like the "real" original-text
                           link but actually resolve to an HTML viewer page,
                           not a PDF -- confirmed live, so deliberately not
                           used here.

Neither element is guaranteed present: a handful of LawDetails pages 404
into the site's own generic error page (confirmed live on ~2/6 sampled
rows, for no discernible reason tied to document type) and simply have no
`h4.center` at all, and roughly a third of *working* pages have no
Translated-document attachment. `_parse_details` returns `(None, [])` for
whatever it can't find rather than raising, so this is a real, expected
"majority but not all" fill rate, not a bug to chase to 100%.

A LawDetails fetch is only worth its own request when the row is actually
new or has changed since the last run, so `discover()` compares each row
against what's already stored (by title/summary/type/dates — the parts a
change to the listing itself would touch) before deciding to fetch. That
comparison intentionally excludes reference_number/pdf_urls themselves, so an
already-enriched row doesn't look "changed" just because a fresh listing-only
parse hasn't populated those fields yet. Normal runs cap at
``max_pages`` (3) and only ever touch new/changed rows; `--backfill` walks
every page once and additionally re-fetches any already-stored row still
missing its reference number or PDF link, to catch older rows a normal run
would never reach.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence

from pydantic import HttpUrl
from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean, content_hash
from .base import BaseScraper, register

_DEFAULT_MAX_PAGES = 3
_BACKFILL_SAFETY_CAP = 500  # hard stop if the endpoint ever fails to return an empty page
_SEARCH_QUERY = "PageNumber={page}&SortDirection=DES"

# "رقم (م/237) وتاريخ 1447/11/3هـ" or "رقم م/51 بتاريخ 23 / 8 / 1426" -- with
# or without parens, and with either "و" or "ب" before "تاريخ" -- both
# confirmed live across real h4.center headings.
_REFERENCE_RE = re.compile(r"رقم\s*\(?\s*([^()\s][^()]{0,20}?)\s*\)?\s*(?:و|ب)?تاريخ")


def _doc_type(title: str) -> DocumentType:
    if title.startswith("لائحة"):
        return DocumentType.REGULATION
    if title.startswith(("نظام", "النظام")):
        return DocumentType.LAW
    return DocumentType.OTHER


def _listing_signature(doc: RegulatoryDocument) -> str:
    """Hash of the fields a fresh listing-only parse can actually see.

    Deliberately excludes reference_number/pdf_urls (only ever set from the
    LawDetails page) so comparing a freshly-parsed row against a previously
    *enriched* stored row doesn't look like a change just because the new
    parse hasn't fetched those fields yet.
    """

    return content_hash(
        doc.title,
        doc.title_en,
        str(doc.doc_type),
        doc.summary,
        doc.effective_date.isoformat() if doc.effective_date else None,
        ",".join(sorted(doc.categories)),
    )


@register("bureau_of_experts")
class BureauOfExpertsScraper(BaseScraper):
    tuned = True

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        max_pages = int(self.source.extra.get("max_pages", _DEFAULT_MAX_PAGES))
        known = self.store.load(self.source.key)

        for base in self.source.start_paths:
            page = 1
            while True:
                if not self.backfill and page > max_pages:
                    break
                if self.backfill and page > _BACKFILL_SAFETY_CAP:
                    self.log.warning("backfill.safety_cap_hit", source=self.source.key, page=page)
                    break

                sep = "&" if "?" in base else "?"
                url = self.abs_url(f"{base}{sep}{_SEARCH_QUERY.format(page=page)}")
                resp = await self.http.get(url)
                self.store.write_raw(self.source.key, f"search_p{page}", resp.text)

                rows = HTMLParser(resp.text).css("div.search_result_item")
                if not rows:
                    break

                for row in rows:
                    draft = self._parse_row(row)
                    if draft is None:
                        continue

                    existing = known.get(draft.uid)
                    if self._needs_detail_fetch(draft, existing):
                        reference_number, pdf_urls = await self._fetch_details(str(draft.url))
                        yield self._enrich(draft, reference_number, pdf_urls)
                    elif existing is not None:
                        yield self._enrich(draft, existing.reference_number, existing.pdf_urls)
                    else:
                        yield draft

                page += 1

    def _needs_detail_fetch(
        self, draft: RegulatoryDocument, existing: RegulatoryDocument | None
    ) -> bool:
        if existing is None:
            return True  # brand new row
        if self.backfill:
            # Retroactively catch older rows a normal run never re-visits.
            return not existing.reference_number or not existing.pdf_urls
        return _listing_signature(existing) != _listing_signature(draft)

    async def _fetch_details(self, url: str) -> tuple[str | None, list[str]]:
        resp = await self.http.get(url)  # same host/client -> same throttle as the listing pages
        slug = url.rstrip("/").split("/")[-2] if "/" in url else "detail"
        self.store.write_raw(self.source.key, f"detail_{slug}", resp.text)
        return self._parse_details(resp.text)

    def _parse_details(self, html: str) -> tuple[str | None, list[str]]:
        tree = HTMLParser(html)

        reference_number = None
        for heading in tree.css("h4.center"):
            match = _REFERENCE_RE.search(clean(heading.text()))
            if match:
                reference_number = match.group(1).strip()
                break

        pdf_urls: list[str] = []
        seen: set[str] = set()
        for link in tree.css('a[href*="/Files/Download/"]'):
            href = link.attributes.get("href") or ""
            if not href:
                continue
            abs_href = self.abs_url(href)
            if abs_href not in seen:
                seen.add(abs_href)
                pdf_urls.append(abs_href)

        return reference_number, pdf_urls

    def _enrich(
        self,
        draft: RegulatoryDocument,
        reference_number: str | None,
        pdf_urls: Sequence[str | HttpUrl],
    ) -> RegulatoryDocument:
        """Rebuild `draft` with reference_number/pdf_urls filled in.

        A fresh construction (rather than `draft.model_copy(update=...)`) so
        `model_post_init` recomputes `content_hash` over the enriched fields
        too -- otherwise the stale hash from the listing-only parse would
        make `upsert_many` think an enriched row keeps "changing" forever.
        """

        return RegulatoryDocument(
            uid=draft.uid,
            source_key=draft.source_key,
            title=draft.title,
            title_en=draft.title_en,
            doc_type=draft.doc_type,
            url=draft.url,
            pdf_urls=pdf_urls or draft.pdf_urls,
            reference_number=reference_number or draft.reference_number,
            summary=draft.summary,
            published_gregorian=draft.published_gregorian,
            published_hijri=draft.published_hijri,
            effective_date=draft.effective_date,
            categories=draft.categories,
            verified=True,
        )

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
            verified=True,
        )
