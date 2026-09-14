"""Saudi Central Bank (SAMA) — www.sama.gov.sa

Rules & circulars live under /*/Laws/ as SharePoint pages, but the listing
is rendered client-side from a REST endpoint under the site's own
`_api/web/lists/...` — a plain HTML fetch of the .aspx page returns an
(almost) empty shell, confirmed by our own snapshots in
data/raw/sama_circulars/. discover() therefore hits that JSON API directly
and pages with $skip/$top, rather than scraping the rendered page.

Each configured `start_paths` entry is a page under a SharePoint site, e.g.
`/ar-sa/Laws/Pages/default.aspx`; the REST API lives at the *site* root, one
level up from `/Pages/...` — `/ar-sa/Laws` in that example. The list is
assumed titled "Laws" (override via `extra.rest_list_title` in
config/sources.yaml if the real list is named differently) and is expected
to expose at least a title, a circular/reference number, an issue date, and
a document link — the exact internal SharePoint column names depend on how
the list was actually built, so `_parse_item` tries a few plausible aliases
for each rather than assuming one schema.

TODO(selectors): if the REST list turns out to use different field names
than `_TITLE_FIELDS`/`_REF_FIELDS`/`_HIJRI_FIELDS`/`_ISO_DATE_FIELDS`/
`_URL_FIELDS` below, add the real ones there; the pagination and JSON
envelope handling shouldn't need to change.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from ..models import DocumentType, RegulatoryDocument
from ..utils.dates import parse_hijri_date
from ..utils.text import clean
from .base import BaseScraper, register

_DEFAULT_PAGE_SIZE = 50
_DEFAULT_MAX_PAGES = 5

_TITLE_FIELDS: tuple[str, ...] = ("Title",)
_REF_FIELDS: tuple[str, ...] = ("CircularNumber", "ReferenceNumber", "Number", "CircularNo")
_HIJRI_FIELDS: tuple[str, ...] = ("HijriDate", "IssueDateHijri", "circular_date_hijri")
_ISO_DATE_FIELDS: tuple[str, ...] = ("IssueDate", "PublishDate", "Modified", "Created")
_URL_FIELDS: tuple[str, ...] = ("DocumentUrl", "FileRef", "Link", "Url")


def _first(item: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for f in fields:
        val = item.get(f)
        if val:
            return val
    return None


def _site_path(start_path: str) -> str:
    """The REST API lives at the SharePoint site root, one level above the
    `/Pages/<page>.aspx` the site actually renders."""

    return start_path.split("/Pages/")[0] if "/Pages/" in start_path else start_path.rstrip("/")


def _iso_to_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


@register("sama")
class SamaScraper(BaseScraper):
    async def discover(self) -> AsyncIterator[RegulatoryDocument]:
        list_title = self.source.extra.get("rest_list_title", "Laws")
        page_size = int(self.source.extra.get("page_size", _DEFAULT_PAGE_SIZE))
        max_pages = int(self.source.extra.get("max_pages", _DEFAULT_MAX_PAGES))

        for start_path in self.source.start_paths:
            site = _site_path(start_path)
            for page in range(max_pages):
                skip = page * page_size
                url = self.abs_url(
                    f"{site}/_api/web/lists/getbytitle('{list_title}')/items"
                    f"?$top={page_size}&$skip={skip}&$orderby=Modified desc"
                )
                resp = await self.http.get(
                    url, headers={"Accept": "application/json;odata=verbose"}
                )
                self.store.write_raw(self.source.key, f"rest_p{page}", resp.text)

                items = self._extract_items(resp.text)
                if not items:
                    break
                for item in items:
                    doc = self._parse_item(item)
                    if doc is not None:
                        yield doc

    @staticmethod
    def _extract_items(raw_json: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw_json)
        except ValueError:
            return []
        # SharePoint's "verbose" OData envelope; a bare "value" list (the
        # newer, "nometadata" shape) and a plain list are also accepted so
        # this keeps working if the site's REST config changes.
        if isinstance(data, dict) and "d" in data:
            return list(data["d"].get("results", []))
        if isinstance(data, dict) and "value" in data:
            return list(data["value"])
        if isinstance(data, list):
            return data
        return []

    def _parse_item(self, item: dict[str, Any]) -> RegulatoryDocument | None:
        title = clean(_first(item, _TITLE_FIELDS) or "")
        if not title:
            return None

        hijri_text = _first(item, _HIJRI_FIELDS)
        hijri, greg = parse_hijri_date(str(hijri_text)) if hijri_text else (None, None)

        iso_value = _first(item, _ISO_DATE_FIELDS)
        if greg is None and iso_value:
            greg = _iso_to_date(str(iso_value))

        link = _first(item, _URL_FIELDS)
        if isinstance(link, dict):  # SharePoint hyperlink field: {"Url": ..., "Description": ...}
            link = link.get("Url")
        if not link:
            item_id = item.get("Id") or item.get("ID")
            if item_id is None:
                return None
            list_title = self.source.extra.get("rest_list_title", "Laws")
            link = f"{self.source.base_url}/Lists/{list_title}/DispForm.aspx?ID={item_id}"

        return RegulatoryDocument(
            source_key=self.source.key,
            title=title,
            doc_type=DocumentType.CIRCULAR,
            url=self.abs_url(str(link)),
            reference_number=_first(item, _REF_FIELDS),
            published_hijri=hijri,
            published_gregorian=greg,
            categories=self.source.categories,
            verified=True,
        )
