"""Shared parsing helpers for scrapers.

`harvest_links` is a deliberately generic first pass: it pulls candidate
document links + nearby dates from a listing page so a new source produces
*something* immediately. Replace with site-specific selectors as you tune
each scraper — the CSS for each portal is noted in its module docstring.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper

_DOC_HINTS = (
    ".pdf", "/law", "/regulation", "/circular", "/rule", "/decision", "/detail", "/article",
)


@dataclass
class LinkCandidate:
    title: str
    url: str
    hijri: str | None = None
    gregorian: object | None = None
    pdf_urls: list[str] = field(default_factory=list)


def harvest_links(html: str, base_url: str) -> Iterator[LinkCandidate]:
    tree = HTMLParser(html)
    seen: set[str] = set()
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base_url, href)
        title = clean(node.text())
        low = url.lower()
        if not title or len(title) < 8:
            continue
        if not any(h in low for h in _DOC_HINTS):
            continue
        if url in seen:
            continue
        seen.add(url)

        container = node.parent.parent if node.parent else node
        context = clean(container.text()) if container else title
        hijri, greg = parse_hijri_date(context)
        pdfs = [url] if low.endswith(".pdf") else []
        yield LinkCandidate(title=title, url=url, hijri=hijri, gregorian=greg, pdf_urls=pdfs)


class GenericListingScraper(BaseScraper):
    """Fetches each `start_path`, snapshots the HTML, and emits every candidate
    link `harvest_links` finds. Subclasses set `default_doc_type` and, as the
    scraper is tuned, override `discover` with real selectors."""

    default_doc_type: DocumentType = DocumentType.OTHER

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            url = self.abs_url(path)
            resp = await self.http.get(url)
            slug = path.strip("/").replace("/", "_") or "index"
            self.store.write_raw(self.source.key, slug, resp.text)
            for cand in harvest_links(resp.text, url):
                yield RegulatoryDocument(
                    source_key=self.source.key,
                    title=cand.title,
                    doc_type=self.default_doc_type,
                    url=cand.url,
                    pdf_urls=cand.pdf_urls,
                    published_hijri=cand.hijri,
                    published_gregorian=cand.gregorian,
                    categories=self.source.categories,
                    verified=False,
                )
