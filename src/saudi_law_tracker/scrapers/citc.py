"""Communications, Space & Technology Commission (CST, formerly CITC) — cst.gov.sa

Regulations index plus public consultations. The site is a Next.js app: the
page embeds its data in a `<script id="__NEXT_DATA__" type="application/json">`
tag, under `props.pageProps.items` — parsing that gives a clean list with
slugs, categories and dates instead of scraping a client-rendered DOM.

TODO(selectors): the exact `pageProps` shape isn't pinned to a stable public
schema, so `_extract_items`/`_parse_item` try a couple of plausible key names
per item (`title`/`titleAr`, `date`/`publishedAt`, `slug`/`id`). If the site's
data shape changes, adjust the alias tuples below rather than the control
flow.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from selectolax.parser import HTMLParser

from ..models import DocumentType, RegulatoryDocument
from ..utils.text import clean
from .base import BaseScraper, register

_TITLE_KEYS: tuple[str, ...] = ("title", "titleAr", "name", "nameAr")
_DATE_KEYS: tuple[str, ...] = ("date", "publishedAt", "publishDate", "createdAt")
_SLUG_KEYS: tuple[str, ...] = ("slug", "id", "url")
_CATEGORY_KEYS: tuple[str, ...] = ("category", "type")


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        val = item.get(k)
        if val:
            return val
    return None


def _iso_to_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _doc_type(category: str | None) -> DocumentType:
    low = (category or "").lower()
    if "consult" in low:
        return DocumentType.PUBLIC_CONSULTATION
    if "framework" in low:
        return DocumentType.FRAMEWORK
    return DocumentType.REGULATION


@register("citc")
class CitcScraper(BaseScraper):
    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        for path in self.source.start_paths:
            url = self.abs_url(path)
            resp = await self.http.get(url)
            slug = path.strip("/").replace("/", "_") or "index"
            self.store.write_raw(self.source.key, slug, resp.text)

            for item in self._extract_items(resp.text):
                doc = self._parse_item(item, path)
                if doc is not None:
                    yield doc

    @staticmethod
    def _extract_items(html: str) -> list[dict[str, Any]]:
        node = HTMLParser(html).css_first("script#__NEXT_DATA__")
        if node is None:
            return []
        try:
            data = json.loads(node.text())
        except ValueError:
            return []
        page_props = data.get("props", {}).get("pageProps", {})
        items = page_props.get("items") or page_props.get("regulations") or []
        return list(items) if isinstance(items, list) else []

    def _parse_item(self, item: dict[str, Any], start_path: str) -> RegulatoryDocument | None:
        title = clean(_first(item, _TITLE_KEYS) or "")
        if not title:
            return None

        slug = _first(item, _SLUG_KEYS)
        url = self.abs_url(f"{start_path.rstrip('/')}/{slug}") if slug else self.abs_url(start_path)

        date_value = _first(item, _DATE_KEYS)
        published = _iso_to_date(date_value) if date_value else None

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=_doc_type(_first(item, _CATEGORY_KEYS)),
            url=url,
            published_gregorian=published,
            categories=self.source.categories,
            verified=True,
        )
