"""Zakat, Tax and Customs Authority (ZATCA) — zatca.gov.sa

Rules & Regulations plus the "Public Consultations" section (draft rules open
for comment — worth flagging early). Site is a headless CMS; pages expose
JSON-LD in a <script type="application/ld+json"> block with datePublished —
prefer that over scraping visible text once tuned.

TODO(selectors): cards under `.card-list .card`; consultation deadline in
`.deadline`. Separate start_path per language keeps AR/EN titles aligned.
"""

from __future__ import annotations

from ..models import DocumentType
from ._common import GenericListingScraper
from .base import register


@register("zatca")
class ZatcaScraper(GenericListingScraper):
    default_doc_type = DocumentType.TAX_RULING
