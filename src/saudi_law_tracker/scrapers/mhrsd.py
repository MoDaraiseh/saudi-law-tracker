"""Ministry of Human Resources & Social Development — hrsd.gov.sa

Tracks the Labor System (نظام العمل) and its ministerial-decision amendments
across the two feeds configured as separate `start_paths`:

  /ar/policies                     consolidated regulations, `.policy-card` items
  /ar/media-center/ministry-news   announcements, `.news-card` items with
                                    `.news-card__date` (Hijri)

Amendments are announced on the news feed before the consolidated policy
text is updated, but that feed carries a lot of unrelated ministry news, so
only titles mentioning the Labor Law / a regulation / a ministerial decision
are kept from it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from selectolax.parser import HTMLParser, Node

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper, register

_LABOR_KEYWORDS = ("نظام العمل", "لائحة", "قرار وزاري")


def _is_labor_related(title: str) -> bool:
    return any(kw in title for kw in _LABOR_KEYWORDS)


@register("mhrsd")
class MhrsdScraper(BaseScraper):
    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            url = self.abs_url(path)
            resp = await self.http.get(url)
            slug = path.strip("/").replace("/", "_") or "index"
            self.store.write_raw(self.source.key, slug, resp.text)

            tree = HTMLParser(resp.text)
            if "polic" in path:
                for card in tree.css(".policy-card"):
                    doc = self._parse_policy_card(card)
                    if doc is not None:
                        yield doc
            elif "news" in path:
                for card in tree.css(".news-card"):
                    doc = self._parse_news_card(card)
                    if doc is not None:
                        yield doc

    def _parse_policy_card(self, card: Node) -> RegulatoryDocument | None:
        link = card.css_first("a")
        if link is None:
            return None
        title = clean(link.text())
        href = link.attributes.get("href") or ""
        if not title or not href:
            return None

        hijri, greg = parse_hijri_date(clean(card.text()))
        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=DocumentType.REGULATION,
            url=self.abs_url(href),
            published_hijri=hijri,
            published_gregorian=greg,
            categories=self.source.categories,
            verified=True,
        )

    def _parse_news_card(self, card: Node) -> RegulatoryDocument | None:
        link = card.css_first("a")
        if link is None:
            return None
        title = clean(link.text())
        href = link.attributes.get("href") or ""
        if not title or not href or not _is_labor_related(title):
            return None

        date_node = card.css_first(".news-card__date")
        hijri, greg = parse_hijri_date(clean(date_node.text())) if date_node else (None, None)
        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=DocumentType.MINISTERIAL_DECISION,
            url=self.abs_url(href),
            published_hijri=hijri,
            published_gregorian=greg,
            categories=self.source.categories,
            verified=True,
        )
