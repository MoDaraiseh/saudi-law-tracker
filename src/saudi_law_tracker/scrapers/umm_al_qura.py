"""Umm Al-Qura — the official gazette (uqn.gov.sa)

New issues appear weekly (Friday). Each issue is a numbered edition with a
Hijri date and a PDF of the full gazette; the table of contents lists the
royal decrees / ministerial resolutions published that week.

TODO(selectors): issues archive at /Pages/Issues.aspx; rows in `#issuesTable
tr` with issue number, Hijri date, and a PDF link in the last cell. Emit one
RegulatoryDocument per issue (GAZETTE_ISSUE); optionally expand the TOC into
child documents later.
"""

from __future__ import annotations

from ..models import DocumentType
from ._common import GenericListingScraper
from .base import register


@register("umm_al_qura")
class UmmAlQuraScraper(GenericListingScraper):
    default_doc_type = DocumentType.GAZETTE_ISSUE
