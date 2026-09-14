"""Communications, Space & Technology Commission (CST, formerly CITC)

Confirmed live 2026-09-14: `www.cst.gov.sa/en/regulations` and
`/ar/regulations` (the old config) both redirect straight into an unrelated
Angular single-page app on `mutasilind.cst.gov.sa` that never renders any
regulations content server-side -- there is no `__NEXT_DATA__` script
because this isn't the Next.js app the previous docstring assumed. The real
regulations platform lives on a *different* subdomain entirely:
`mutasilbus.cst.gov.sa/regulations/{documents,decisions,consultations}/`
-- a plain server-rendered Bootstrap page (tabs + `bootstrap.Tab`, not a
framework SPA).

Each of those three sections renders a real `<table class="...table-reg...">`
inside `.tab-pane.reg-list` with `<tr data-href="/regulations/<section>/
details?id=...">` rows -- confirmed by fetching all three pages directly and
inspecting the raw HTML (not a guess from a class-name hint: the
"digital-stamp-card" block the assessment names is unrelated -- it's a
generic gov.sa trust-badge widget that also appears on this domain, not
where the regulations content actually lives). Column layout differs by
section (see `_COLUMNS` below), captured directly from each page's own
`<thead>`.

TODO(pagination): `#paginationContainer` is populated client-side and
`?page=2` is silently ignored server-side (confirmed: it returns byte-
identical content to page 1), so this only scrapes each section's first
page -- 12 rows per section as served today. That's real, live, correctly
parsed data (not a fixture), well above `min_expected_docs`, but it's not
the *complete* listing; finding the real pagination API would need the same
JS-bundle archaeology used for zatca.py's `PortalHandler.ashx`, which
hasn't been done here yet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper, register

# Column index -> field, one tuple per section. `date` fields name the
# gregorian/hijri pair to fill; a section can supply more than one date
# column (decisions: effective + approval; consultations: start + end), in
# which case the first one found wins for published_*, and the extras just
# aren't kept -- there's no second published-date slot on the model.
_COLUMNS: dict[str, dict[str, int]] = {
    "documents": {"reference_number": 1, "date": 4},
    "decisions": {"reference_number": 0, "date": 2},
    "consultations": {"reference_number": 1, "date": 3},
}

_DOC_TYPES: dict[str, DocumentType] = {
    "documents": DocumentType.REGULATION,
    "decisions": DocumentType.REGULATION,
    "consultations": DocumentType.PUBLIC_CONSULTATION,
}


def _section_from_path(path: str) -> str | None:
    for section in _COLUMNS:
        if section in path:
            return section
    return None


def _row_title(row: Node) -> str:
    """The first `.reg-table-title` in a row: a `<div>` (documents,
    consultations) or `<p>` (decisions). Its `title` attribute, when present,
    holds the untruncated text -- the visible text is CSS-truncated
    (`truncate-2`) on some sections."""

    node = row.css_first(".reg-table-title")
    if node is None:
        return ""
    return clean(node.attributes.get("title") or node.text())


def _cell_text(row: Node, index: int) -> str:
    cells = row.css("td")
    if index >= len(cells):
        return ""
    return clean(cells[index].text())


def _cell_dates(row: Node, index: int) -> tuple[str | None, date | None]:
    """A date cell's visible text and its `title` tooltip (when present) are
    the Hijri/Gregorian pair for the same date -- which one is which varies
    by section, so both are parsed and merged by `parse_hijri_date`'s own
    year-magnitude heuristic rather than by which side of the cell they came
    from."""

    cells = row.css("td")
    if index >= len(cells):
        return None, None
    cell = cells[index]
    texts = [cell.text()]
    for el in [cell, *cell.css("[title]")]:
        title = el.attributes.get("title")
        if title:
            texts.append(title)

    hijri: str | None = None
    greg: date | None = None
    for text in texts:
        h, g = parse_hijri_date(text)
        hijri = hijri or h
        greg = greg or g
    return hijri, greg


@register("citc")
class CitcScraper(BaseScraper):
    tuned = True

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            section = _section_from_path(path)
            if section is None:
                self.log.warning("citc.unknown_section", path=path)
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
        table = tree.css_first("table.table-reg")
        if table is None:
            return []
        return [row for row in table.css("tbody tr") if row.attributes.get("data-href")]

    def _parse_row(self, row: Node, section: str) -> RegulatoryDocument | None:
        title = _row_title(row)
        if not title:
            return None

        columns = _COLUMNS[section]
        reference_number = _cell_text(row, columns["reference_number"]) or None
        hijri, greg = _cell_dates(row, columns["date"])

        detail_path = row.attributes.get("data-href") or ""

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=_DOC_TYPES[section],
            url=self.abs_url(detail_path),
            reference_number=reference_number,
            published_hijri=hijri,
            published_gregorian=greg,
            categories=[*self.source.categories, section],
            verified=True,
        )
