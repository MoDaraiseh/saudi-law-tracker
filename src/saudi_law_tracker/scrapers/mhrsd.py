"""Ministry of Human Resources & Social Development — hrsd.gov.sa

Tracks the Labor System (نظام العمل) and its ministerial-decision amendments.
Two feeds matter: /ar/policies (consolidated regulations) and the news feed
where amendments are announced before the consolidated text updates.

TODO(selectors): policy cards `.policy-card`; news items `.news-card` with
`.news-card__date` (Hijri). Consider filtering news titles for
'نظام العمل' / 'لائحة' / 'قرار وزاري'.
"""

from __future__ import annotations

from ..models import DocumentType
from ._common import GenericListingScraper
from .base import register


@register("mhrsd")
class MhrsdScraper(GenericListingScraper):
    default_doc_type = DocumentType.MINISTERIAL_DECISION
