"""Saudi Central Bank (SAMA) — www.sama.gov.sa

Rules & circulars live under /*/Laws/ as SharePoint pages. Listings are
often rendered client-side from a REST endpoint
(`/_api/web/lists/...`); if the HTML pass returns nothing, switch discover()
to hit that JSON API and page with `$skip`/`$top`.

TODO(selectors): document rows in `.ms-rteTable-default tr` or `.law-item`;
circular number + Hijri date in the first two cells.
"""

from __future__ import annotations

from ..models import DocumentType
from ._common import GenericListingScraper
from .base import register


@register("sama")
class SamaScraper(GenericListingScraper):
    default_doc_type = DocumentType.CIRCULAR
