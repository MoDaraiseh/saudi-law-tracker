"""Communications, Space & Technology Commission (CST, formerly CITC) — cst.gov.sa

Regulations index plus public consultations. Next.js site: the listing is in
`__NEXT_DATA__` JSON at the bottom of the page — parse that script tag for a
clean list with slugs, categories and ISO dates instead of DOM scraping.

TODO(selectors): `#__NEXT_DATA__` -> props.pageProps.items[].
"""

from __future__ import annotations

from ..models import DocumentType
from ._common import GenericListingScraper
from .base import register


@register("citc")
class CitcScraper(GenericListingScraper):
    default_doc_type = DocumentType.REGULATION
