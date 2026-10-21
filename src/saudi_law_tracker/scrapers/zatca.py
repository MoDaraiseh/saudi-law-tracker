"""Zakat, Tax and Customs Authority (ZATCA) — zatca.gov.sa

Confirmed live 2026-09-14: the previously configured
`/{lang}/RulesRegulations/Pages/default.aspx` listing 404s (redirects to
PageNotFound), and even the real regulations landing page
(`RulesRegulations/Pages/rules.aspx`) is just three category-landing cards
(Taxes, Agreements, Information Exchange) — not a list of individual
regulations. Each category's own page renders its cards client-side from a
skeleton placeholder ("Media cards will be loaded dynamically via
rules-card.js"); `main.js`'s `rulesCards()` function reveals the real data
source, a JSON endpoint:

    /{lang}/_LAYOUTS/15/GAZTInternet/PortalHandler.ashx
        ?op=LoadItems&listUrl=/{lang}/RulesRegulations/{category}/Pages&viewName=Home

Confirmed working (viewName=Home) for category in {Taxes, Agreements} — VAT
and InformationExchange 500 with "the specified view is invalid" for that
view name, and UnderConsultations returns `null` (no live consultations
right now, or a different view is needed there; not pursued here). Each
item gives `Title`, `LinkFilename` (-> the leaf page's own URL) and
`Visibility` ("0" = hidden, filtered out) — but no date field, despite
main.js's own transform code referencing `ArticleStartDate`; that column is
evidently unpopulated on the live list.

The only place a date actually appears is server-rendered on each item's own
leaf page, in a "Last Update: <date> Saudi Arabia Time" footer
(`#ctl00_ucLastModifiedDate_lastUpdateDiv`) — confirmed present and
consistently formatted across every leaf page checked. This is a
last-modified timestamp, not necessarily the original issuance date, so it
goes into `last_modified`, never `published_gregorian`/`published_hijri` —
a page can be re-saved (typo fix, reformatting) long after the ruling it
describes actually took effect, and reporting that as the issuance date
would silently overstate how current the content is. (Some leaf pages also
embed the real Hijri issuance date + decree number in free text inside
their `<meta name="description">`, e.g. "...dated 7-7-1440H", but the
phrasing isn't consistent enough across pages to parse reliably yet — see
TODO.) Since the date only exists behind that per-item fetch, there's no
cheaper "unchanged, skip it" signal available the way bureau_of_experts
has; `extra.max_items` in config/sources.yaml bounds how many of each
category's items get dated per run.

Only the English (`/en`) pages are scraped for now — the Arabic leaf pages'
"Last Update" footer uses Arabic month names (or Hijri), which this scraper
doesn't parse yet; see TODO.

TODO(selectors): parse Arabic-locale "آخر تحديث" dates so `/ar` can be
scraped too; extract the Hijri issuance date + decree number embedded in
each leaf page's meta description where present.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from selectolax.parser import HTMLParser

from ..models import DocumentType, RegulatoryDocument
from ..utils.text import clean
from .base import BaseScraper, register

_DEFAULT_MAX_ITEMS = 30
_LANG = "en"
_CATEGORIES: tuple[str, ...] = ("Taxes", "Agreements")
_CATEGORY_DOC_TYPE: dict[str, DocumentType] = {
    "Taxes": DocumentType.TAX_RULING,
    "Agreements": DocumentType.REGULATION,
}
_LAST_UPDATE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})")


def _api_path(category: str) -> str:
    return (
        f"/{_LANG}/_LAYOUTS/15/GAZTInternet/PortalHandler.ashx"
        f"?op=LoadItems&listUrl=/{_LANG}/RulesRegulations/{category}/Pages&viewName=Home"
    )


def _leaf_path(category: str, link_filename: str) -> str:
    return f"/{_LANG}/RulesRegulations/{category}/Pages/{link_filename}"


def _parse_last_modified(html: str) -> date | None:
    node = HTMLParser(html).css_first("#ctl00_ucLastModifiedDate_lastUpdateDiv")
    if node is None:
        return None
    match = _LAST_UPDATE_RE.search(node.text())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %b %Y").date()
    except ValueError:
        return None


@register("zatca")
class ZatcaScraper(BaseScraper):
    tuned = True

    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        max_items = int(self.source.extra.get("max_items", _DEFAULT_MAX_ITEMS))

        for category in _CATEGORIES:
            api_url = self.abs_url(_api_path(category))
            resp = await self.http.get(api_url)
            self.store.write_raw(self.source.key, f"api_{category.lower()}", resp.text)

            for item in self._extract_items(resp.text)[:max_items]:
                doc = await self._build_doc(item, category)
                if doc is not None:
                    yield doc

    @staticmethod
    def _extract_items(raw_json: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw_json)
        except ValueError:
            return []
        if not isinstance(data, list):
            return []  # e.g. the {"Message": "..."} error shape for an invalid view, or null
        return [
            item
            for item in data
            if isinstance(item, dict)
            and item.get("Visibility") != "0"
            and item.get("FileLeafRef") != "default.aspx"
        ]

    async def _build_doc(self, item: dict[str, Any], category: str) -> RegulatoryDocument | None:
        title = clean(item.get("Title") or "")
        link_filename = item.get("LinkFilename") or item.get("FileLeafRef") or ""
        if not title or not link_filename:
            return None

        leaf_url = self.abs_url(_leaf_path(category, link_filename))
        resp = await self.http.get(leaf_url)
        self.store.write_raw(self.source.key, f"leaf_{category.lower()}_{link_filename}", resp.text)

        last_modified = _parse_last_modified(resp.text)
        if last_modified is None:
            return None  # no date signal at all -> doesn't meet the "dated row" bar

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=_CATEGORY_DOC_TYPE.get(category, DocumentType.TAX_RULING),
            url=leaf_url,
            last_modified=last_modified,
            categories=self.source.categories,
            verified=True,
        )
