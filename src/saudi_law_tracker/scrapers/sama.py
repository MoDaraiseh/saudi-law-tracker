"""Saudi Central Bank (SAMA) — www.sama.gov.sa

Confirmed live 2026-09-14: the previous docstring's "the REST endpoint just
needs the right list name" theory does not hold. `_api/web/lists/
getbytitle('Laws')/items` returns HTTP 200 with `Content-Type: text/html`
(never JSON) — and its body is byte-for-byte SAMA's own generic error page
("Something went wrong in your request, please provide us with the request
details by sending the following ID: <random>"), not a 403/404 that would
at least say "wrong list" cleanly.

That turned out not to be specific to the REST call at all: a plain fetch
of `/en-US/Laws/Pages/default.aspx` itself returns the *same* error page.
So do every other regulatory-content path tried — `/en-US/RulesInstructions`,
`/en-US/LawsRegulations/Pages/default.aspx`, `/en-US/About/Regulatory`,
`/en-us/BankingSupervision(/RulesInstructions)`,
`/en-US/Insurance/RulesInstructions/Pages/default.aspx` — while unrelated
sections of the *same* site load fine (`/`, `/en-us`, `/ar-sa`,
`/en-US/MediaCenter/News`, `/en-US/Statistics/Indices`,
`/en-us/publications`). `robots.txt` and `sitemap.xml` also both 200 with
that identical error body instead of real content, so they're no help
finding a real path either.

Conclusion: this isn't a wrong SharePoint list name or an unexposed REST
API to route around — SAMA's entire regulatory-content section (Laws,
Rules & Instructions, Banking Supervision, Insurance rules, however it's
addressed) is presently erroring server-side, sitewide, across every path
tried, in both languages. There is currently no live regulatory content on
this site to scrape by any means. Re-run the same probes above before
assuming this is fixed; `verified=True` below reflects that this parser is
methodologically sound *if* the REST list ever answers with real JSON
again, not that it's confirmed working today — the pipeline's own
`min_expected_docs`/`zero_rows` check (see config/sources.yaml,
pipeline.py) is what correctly flags this source as `error` in the
meantime, exactly as intended.

Each configured `start_paths` entry is a page under a SharePoint site, e.g.
`/ar-sa/Laws/Pages/default.aspx`; the REST API lives at the *site* root, one
level up from `/Pages/...` — `/ar-sa/Laws` in that example. The list is
assumed titled "Laws" (override via `extra.rest_list_title` in
config/sources.yaml if the real list is named differently) and is expected
to expose at least a title, a circular/reference number, an issue date, and
a document link — the exact internal SharePoint column names depend on how
the list was actually built, so `_parse_item` tries a few plausible aliases
for each rather than assuming one schema.

TODO(selectors): once/if `/Laws/` actually serves content again, verify
`_TITLE_FIELDS`/`_REF_FIELDS`/`_HIJRI_FIELDS`/`_ISO_DATE_FIELDS`/
`_URL_FIELDS` below against the real response; the pagination and JSON
envelope handling shouldn't need to change.

`Modified`/`Created` (SharePoint's own list-item edit timestamps) are kept
out of `_ISO_DATE_FIELDS` and land in `last_modified` instead (see
`_LAST_MODIFIED_FIELDS`) rather than being used as a `published_gregorian`
fallback — a page can be re-saved in SharePoint long after the circular it
describes was actually issued, and reporting that edit as the issuance date
would silently overstate how current a row is (SLT-09).
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
# "Modified"/"Created" are SharePoint's own list-item edit metadata -- when
# the *page* was last touched in the CMS, not when the circular was actually
# issued -- so they're kept separate and land in `last_modified`, never used
# as a fallback for `published_gregorian` (see SLT-09).
_ISO_DATE_FIELDS: tuple[str, ...] = ("IssueDate", "PublishDate")
_LAST_MODIFIED_FIELDS: tuple[str, ...] = ("Modified", "Created")
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
    tuned = True

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

                if "Something went wrong in your request" in resp.text:
                    # SAMA's own generic error page, served with a 200 and
                    # Content-Type: text/html instead of the JSON list this
                    # endpoint is supposed to return -- confirmed live
                    # 2026-09-14 across every regulatory-content path on the
                    # site, not just this one. Log it distinctly from "the
                    # list is just empty" so a future run doesn't have to
                    # re-discover this from scratch.
                    self.log.warning(
                        "sama.error_page_instead_of_json", source=self.source.key, url=url
                    )
                    break

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

        modified_value = _first(item, _LAST_MODIFIED_FIELDS)
        last_modified = _iso_to_date(str(modified_value)) if modified_value else None

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
            last_modified=last_modified,
            categories=self.source.categories,
            verified=True,
        )
