"""Umm Al-Qura — the official gazette (uqn.gov.sa)

New issues appear weekly (Friday). The issues archive at `/Pages/Issues.aspx`
(see config/sources.yaml's `start_paths`) lists them in `#issuesTable tr`:
issue number and Hijri date in the first two cells, and a PDF of the full
gazette linked from the last cell. One RegulatoryDocument is emitted per
issue (GAZETTE_ISSUE); the table of contents inside each PDF (the individual
royal decrees / ministerial resolutions published that week) is not expanded
into child documents yet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper, register


@register("umm_al_qura")
class UmmAlQuraScraper(BaseScraper):
    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            url = self.abs_url(path)
            resp = await self.http.get(url)
            slug = path.strip("/").replace("/", "_") or "index"
            self.store.write_raw(self.source.key, slug, resp.text)

            for row in HTMLParser(resp.text).css("#issuesTable tr"):
                doc = self._parse_row(row)
                if doc is not None:
                    yield doc

    def _parse_row(self, row: Node) -> RegulatoryDocument | None:
        cells = row.css("td")
        if len(cells) < 2:
            return None  # header row (th, not td) or malformed

        issue_number = clean(cells[0].text())
        if not issue_number:
            return None
        hijri, greg = parse_hijri_date(clean(cells[1].text()))

        pdf_link = cells[-1].css_first("a[href]")
        pdf_href = pdf_link.attributes.get("href") if pdf_link else None
        if not pdf_href:
            return None
        pdf_url = self.abs_url(pdf_href)

        return RegulatoryDocument(
            source_key=self.source.key,
            title=f"جريدة أم القرى - العدد {issue_number}",
            doc_type=DocumentType.GAZETTE_ISSUE,
            url=pdf_url,
            pdf_urls=[pdf_url],
            reference_number=issue_number,
            published_hijri=hijri,
            published_gregorian=greg,
            categories=self.source.categories,
            verified=True,
        )
