"""Core data models for tracked regulatory documents."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl

from .utils.text import content_hash as _hash_content


class DocumentType(StrEnum):
    LAW = "law"
    REGULATION = "regulation"
    ROYAL_DECREE = "royal_decree"
    MINISTERIAL_DECISION = "ministerial_decision"
    CIRCULAR = "circular"
    RULE = "rule"
    TAX_RULING = "tax_ruling"
    GUIDELINE = "guideline"
    FRAMEWORK = "framework"
    PUBLIC_CONSULTATION = "public_consultation"
    GAZETTE_ISSUE = "gazette_issue"
    NEWS = "news"
    OTHER = "other"


class RegulatoryDocument(BaseModel):
    """A single publication discovered from a source.

    Identity is ``source_key`` + canonical ``url`` + publication date: a document
    re-published at a new date (an amended regulation, a reissued circular) is a
    genuinely new entry, while a re-scrape of the same URL and date maps back to
    the existing row. `content_hash` covers the display fields, so a run can tell
    a substantive change from an unchanged re-scrape. Both are derived in
    `model_post_init` unless a scraper sets them explicitly.
    """

    uid: str = ""
    source_key: str
    title: str
    title_en: str | None = None
    doc_type: DocumentType = DocumentType.OTHER
    url: HttpUrl
    pdf_urls: list[HttpUrl] = Field(default_factory=list)
    reference_number: str | None = None
    summary: str | None = None

    published_gregorian: date | None = None
    published_hijri: str | None = None
    effective_date: date | None = None

    categories: list[str] = Field(default_factory=list)
    raw_html_path: str | None = None
    content_hash: str | None = None

    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))

    verified: bool = False
    """True only for scrapers tuned with source-specific selectors; the
    generic listing scraper always emits False. Callers must not cite an
    unverified row as fact — see saudi-law-agent.md."""

    def publication_key(self) -> str:
        """Stable string for the publication date, either calendar."""

        if self.published_gregorian is not None:
            return self.published_gregorian.isoformat()
        return self.published_hijri or ""

    @property
    def display_date(self) -> str:
        """Human-readable publication date for summaries and notifications."""

        if self.published_hijri:
            return f"{self.published_hijri} AH"
        if self.published_gregorian is not None:
            return self.published_gregorian.isoformat()
        return "date n/a"

    def compute_uid(self) -> str:
        raw = f"{self.source_key}|{str(self.url)}|{self.publication_key()}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def compute_content_hash(self) -> str:
        return _hash_content(
            self.title,
            self.title_en,
            str(self.doc_type),
            self.summary,
            self.reference_number,
            self.effective_date.isoformat() if self.effective_date else None,
            ",".join(sorted(str(u) for u in self.pdf_urls)),
            ",".join(sorted(self.categories)),
        )

    def model_post_init(self, __context: object) -> None:
        if not self.uid:
            object.__setattr__(self, "uid", self.compute_uid())
        if not self.content_hash:
            object.__setattr__(self, "content_hash", self.compute_content_hash())


class ScrapeResult(BaseModel):
    """Outcome of running one source's scraper once."""

    source_key: str
    started_at: datetime
    finished_at: datetime
    documents: list[RegulatoryDocument] = Field(default_factory=list)
    new_uids: list[str] = Field(default_factory=list)
    updated_uids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
