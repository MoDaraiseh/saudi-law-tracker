"""Umm Al-Qura — the official gazette (uqn.gov.sa)

Confirmed live 2026-09-14: `/Pages/Issues.aspx` (the previous config's path)
404s -- and that 404 page is itself ~746KB, which is almost certainly the
"746KB page" the assessment is describing; `#issuesTable` was never going to
be on it. The real archive lives at `/archive`, linked from the site's own
homepage nav, and is plain server-rendered HTML (no framework, no
`__NEXT_DATA__`) -- a `.ummalqura-archive-pagination` widget containing one
`a.article-wrapper` per issue:

  <a href="/digital?date=2026-09-11" class="article-wrapper"
     title="uploads/pdf/2026/09/11/ummalqura_pdf-20260911-1.pdf?ts=193509">
    <h2 class="article-title">العدد 5182</h2>
  </a>

Three real fields fall out of that one element: the Gregorian date is a
plain query param on `href` (no Hijri<->Gregorian conversion needed), the
issue number is the trailing digits of `.article-title`, and the `title`
attribute is the PDF's storage path -- but NOT a working URL by itself
(confirmed live: fetching `{base_url}/<that path>` 404s). The real download
goes through a CDN proxy, confirmed by following an issue's own `/digital`
detail page and checking the PDF link it actually renders:
`/cdn/?url=<path>&<original query>` (the same proxy the archive page's own
issue-cover images use). `_cdn_url` reproduces that rewrite rather than
linking the storage path directly.

Pagination is real (unlike CST's client-side-only `#paginationContainer`):
`/archive?pgno=2` etc. are plain server-rendered links in the page's own
`.pager`, confirmed to return a different, sequential set of issues.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date
from urllib.parse import parse_qs, urlparse

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.text import clean
from .base import BaseScraper, register

_DEFAULT_MAX_PAGES = 3
_ISSUE_NUMBER_RE = re.compile(r"(\d+)")


def _date_from_href(href: str) -> date | None:
    """`/digital?date=2026-09-11` -- the Gregorian date is given directly as
    a query param, not embedded in text that needs parsing."""

    query = parse_qs(urlparse(href).query)
    values = query.get("date")
    if not values:
        return None
    value = values[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _issue_number(title: str) -> str | None:
    m = _ISSUE_NUMBER_RE.search(title)
    return m.group(1) if m else None


def _cdn_url(raw_path: str) -> str:
    """The `title` attribute is a bare storage path with its own `?ts=...`
    query string (e.g. `uploads/pdf/.../x.pdf?ts=193509`); the site's real
    download link folds that into a `/cdn/?url=` proxy query instead
    (`/cdn/?url=uploads/pdf/.../x.pdf&ts=193509`) -- confirmed by fetching an
    issue's own detail page and reading off its actual PDF link."""

    return f"cdn/?url={raw_path.replace('?', '&', 1)}"


@register("umm_al_qura")
class UmmAlQuraScraper(BaseScraper):
    tuned = True

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        max_pages = int(self.source.extra.get("max_pages", _DEFAULT_MAX_PAGES))

        for start_path in self.source.start_paths:
            for page in range(1, max_pages + 1):
                path = start_path if page == 1 else f"{start_path}?pgno={page}"
                url = self.abs_url(path)
                resp = await self.http.get(url)
                self.store.write_raw(self.source.key, f"p{page}", resp.text)

                items = self._extract_items(resp.text)
                if not items:
                    break
                for item in items:
                    doc = self._parse_item(item)
                    if doc is not None:
                        yield doc

    @staticmethod
    def _extract_items(html: str) -> list[Node]:
        tree = HTMLParser(html)
        return tree.css(".ummalqura-archive-pagination .article-wrapper")

    def _parse_item(self, node: Node) -> RegulatoryDocument | None:
        href = node.attributes.get("href") or ""
        title_node = node.css_first(".article-title")
        title_text = clean(title_node.text()) if title_node is not None else ""
        if not href or not title_text:
            return None

        issue_number = _issue_number(title_text)
        greg = _date_from_href(href)

        pdf_path = node.attributes.get("title") or ""
        pdf_urls = [self.abs_url(_cdn_url(pdf_path))] if pdf_path else []

        return RegulatoryDocument(
            source_key=self.source.key,
            title=f"جريدة أم القرى - {title_text}",
            doc_type=DocumentType.GAZETTE_ISSUE,
            url=self.abs_url(href),
            pdf_urls=pdf_urls,
            reference_number=issue_number,
            published_gregorian=greg,
            categories=self.source.categories,
            verified=True,
        )
