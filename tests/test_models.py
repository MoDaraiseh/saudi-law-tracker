from __future__ import annotations

from datetime import date

from saudi_law_tracker.models import DocumentType, RegulatoryDocument


def _doc(**overrides: object) -> RegulatoryDocument:
    defaults: dict[str, object] = {
        "source_key": "demo",
        "title": "عنوان",
        "doc_type": DocumentType.LAW,
        "url": "https://example.gov.sa/x",
    }
    defaults.update(overrides)
    return RegulatoryDocument(**defaults)


def test_last_modified_defaults_to_none():
    assert _doc().last_modified is None


def test_display_date_prefers_hijri_over_everything():
    doc = _doc(
        published_hijri="1445-10-22",
        published_gregorian=date(2024, 5, 1),
        last_modified=date(2024, 9, 1),
    )
    assert doc.display_date == "1445-10-22 AH"


def test_display_date_prefers_gregorian_over_last_modified():
    doc = _doc(published_gregorian=date(2024, 5, 1), last_modified=date(2024, 9, 1))
    assert doc.display_date == "2024-05-01"


def test_display_date_falls_back_to_last_modified_labeled_explicitly():
    """SLT-09: a page-edit timestamp must never read as a publication date --
    the fallback text has to say so, not just print a bare date."""

    doc = _doc(last_modified=date(2024, 9, 1))
    assert doc.display_date == "last modified 2024-09-01, issuance date unknown"


def test_display_date_is_n_a_when_nothing_is_known():
    assert _doc().display_date == "date n/a"


def test_publication_key_does_not_fall_back_to_last_modified():
    """Identity is meant to track the real publication date, not an edit
    timestamp -- a document with only last_modified has no publication_key."""

    doc = _doc(last_modified=date(2024, 9, 1))
    assert doc.publication_key() == ""


def test_content_hash_changes_when_last_modified_changes():
    older = _doc(last_modified=date(2024, 1, 1))
    newer = _doc(last_modified=date(2024, 9, 1))
    assert older.content_hash != newer.content_hash
