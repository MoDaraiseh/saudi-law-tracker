from __future__ import annotations

import sqlite3
from datetime import date

from saudi_law_tracker.models import DocumentType, RegulatoryDocument
from saudi_law_tracker.storage import _COLUMNS, DocumentStore


def _doc(url: str, title: str, h: str) -> RegulatoryDocument:
    return RegulatoryDocument(
        source_key="demo",
        title=title,
        doc_type=DocumentType.CIRCULAR,
        url=url,
        content_hash=h,
    )


def _scraped(
    url: str,
    title: str,
    *,
    published: date | None = None,
    summary: str | None = None,
) -> RegulatoryDocument:
    """A document as a scraper builds it: uid + content_hash derived, not passed."""

    return RegulatoryDocument(
        source_key="demo",
        title=title,
        doc_type=DocumentType.CIRCULAR,
        url=url,
        summary=summary,
        published_gregorian=published,
    )


def test_upsert_detects_new_then_unchanged_then_updated(settings):
    store = DocumentStore(settings)
    d = _doc("https://example.gov.sa/a", "Rule A", "h1")

    new, updated = store.upsert_many("demo", [d])
    assert new and not updated

    new, updated = store.upsert_many("demo", [_doc("https://example.gov.sa/a", "Rule A", "h1")])
    assert not new and not updated

    new, updated = store.upsert_many("demo", [_doc("https://example.gov.sa/a", "Rule A v2", "h2")])
    assert not new and updated

    assert len(store.load("demo")) == 1


def test_uid_is_stable_across_instances():
    a = _doc("https://example.gov.sa/x", "T", "h")
    b = _doc("https://example.gov.sa/x", "different title", "other")
    assert a.uid == b.uid


def test_uid_keys_on_url_plus_publication_date():
    a = _scraped("https://example.gov.sa/law/1", "Law", published=date(2024, 1, 1))
    later = _scraped("https://example.gov.sa/law/1", "Law", published=date(2024, 6, 1))
    reworded = _scraped("https://example.gov.sa/law/1", "Law amended", published=date(2024, 1, 1))

    assert a.uid != later.uid  # same URL, new publication date -> new entry
    assert a.uid == reworded.uid  # same URL + date -> same entry, other fields aside


def test_republished_at_new_date_is_flagged_new(settings):
    store = DocumentStore(settings)
    v1 = _scraped("https://example.gov.sa/x", "Circular X", published=date(2024, 1, 1))
    new, updated = store.upsert_many("demo", [v1])
    assert new == [v1.uid] and not updated

    v2 = _scraped("https://example.gov.sa/x", "Circular X", published=date(2024, 3, 1))
    new, updated = store.upsert_many("demo", [v1, v2])
    assert new == [v2.uid] and not updated
    assert len(store.load("demo")) == 2


def test_delete_removes_only_the_named_uid(settings):
    store = DocumentStore(settings)
    v1 = _scraped("https://example.gov.sa/x", "Circular X", published=date(2024, 1, 1))
    v2 = _scraped("https://example.gov.sa/y", "Circular Y", published=date(2024, 2, 1))
    store.upsert_many("demo", [v1, v2])
    assert store.count("demo") == 2

    store.delete(v1.uid)

    remaining = store.load("demo")
    assert store.count("demo") == 1
    assert v1.uid not in remaining
    assert v2.uid in remaining


def test_content_change_at_same_date_is_flagged_updated(settings):
    store = DocumentStore(settings)
    base = _scraped("https://e.gov.sa/x", "Title", published=date(2024, 1, 1), summary="draft")
    store.upsert_many("demo", [base])

    same = _scraped("https://e.gov.sa/x", "Title", published=date(2024, 1, 1), summary="draft")
    new, updated = store.upsert_many("demo", [same])
    assert not new and not updated

    edited = _scraped("https://e.gov.sa/x", "Title", published=date(2024, 1, 1), summary="final")
    new, updated = store.upsert_many("demo", [edited])
    assert not new and updated == [edited.uid]


def test_regulations_table_matches_model_fields(settings):
    DocumentStore(settings)
    with sqlite3.connect(settings.db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(regulations)")]

    model_fields = set(RegulatoryDocument.model_fields)
    assert set(cols) == model_fields
    assert set(_COLUMNS) == model_fields


def test_document_round_trips_through_sqlite(settings):
    store = DocumentStore(settings)
    doc = RegulatoryDocument(
        source_key="demo",
        title="نظام العمل",
        title_en="Labor Law",
        doc_type=DocumentType.LAW,
        url="https://example.gov.sa/labor",
        pdf_urls=["https://example.gov.sa/labor.pdf"],
        reference_number="M/51",
        summary="ملخص",
        published_gregorian=date(2024, 5, 1),
        published_hijri="1445-10-22",
        effective_date=date(2024, 8, 1),
        last_modified=date(2024, 9, 1),
        categories=["law", "labor"],
    )
    store.upsert_many("demo", [doc])

    (loaded,) = store.load("demo").values()
    # first_seen / last_seen are stamped by the store; everything else round-trips.
    fields = {"first_seen", "last_seen"}
    assert loaded.model_dump(exclude=fields) == doc.model_dump(exclude=fields)
    assert loaded.pdf_urls == doc.pdf_urls
    assert loaded.categories == ["law", "labor"]
    assert loaded.published_gregorian == date(2024, 5, 1)
    assert loaded.last_modified == date(2024, 9, 1)
    assert store.count("demo") == 1


def _seed_for_query(store: DocumentStore) -> None:
    store.upsert_many(
        "mhrsd_labor",
        [
            RegulatoryDocument(
                source_key="mhrsd_labor",
                title="تعديل نظام العمل",
                doc_type=DocumentType.MINISTERIAL_DECISION,
                url="https://hrsd.gov.sa/1",
                summary="أحكام ساعات العمل",
                published_gregorian=date(2024, 6, 1),
                categories=["ministerial_decision", "labor_law_amendment"],
            )
        ],
    )
    store.upsert_many(
        "zatca_updates",
        [
            RegulatoryDocument(
                source_key="zatca_updates",
                title="لائحة ضريبة القيمة المضافة",
                doc_type=DocumentType.REGULATION,
                url="https://zatca.gov.sa/1",
                published_gregorian=date(2023, 1, 15),
                categories=["tax_ruling", "regulation"],
            ),
            RegulatoryDocument(
                source_key="zatca_updates",
                title="دليل الفوترة الإلكترونية",
                doc_type=DocumentType.GUIDELINE,
                url="https://zatca.gov.sa/2",
                categories=["guideline"],
            ),
        ],
    )


def test_query_by_sector_matches_source_key_or_category(settings):
    store = DocumentStore(settings)
    _seed_for_query(store)

    labor = store.query(sector="labor")
    assert [d.source_key for d in labor] == ["mhrsd_labor"]

    tax = store.query(sector="tax")  # via the tax_ruling category, not the key
    assert {d.url.host for d in tax} == {"zatca.gov.sa"}
    assert len(tax) == 1


def test_query_filters_compose(settings):
    store = DocumentStore(settings)
    _seed_for_query(store)

    assert store.query(doc_types=["regulation", "guideline"]) and all(
        d.doc_type in {DocumentType.REGULATION, DocumentType.GUIDELINE}
        for d in store.query(doc_types=["regulation", "guideline"])
    )
    assert [d.title for d in store.query(text="نظام العمل")] == ["تعديل نظام العمل"]
    assert [d.url.path for d in store.query(since=date(2024, 1, 1))] == ["/1"]
    assert store.query(until=date(2023, 12, 31))[0].published_gregorian == date(2023, 1, 15)
    assert len(store.query(limit=1)) == 1


def test_query_orders_newest_first_then_undated(settings):
    store = DocumentStore(settings)
    _seed_for_query(store)

    dates = [d.published_gregorian for d in store.query()]
    assert dates == [date(2024, 6, 1), date(2023, 1, 15), None]


def test_query_filters_by_verified(settings):
    store = DocumentStore(settings)
    store.upsert_many(
        "demo",
        [
            RegulatoryDocument(
                source_key="demo",
                title="Verified doc",
                doc_type=DocumentType.LAW,
                url="https://example.gov.sa/verified",
                verified=True,
            ),
            RegulatoryDocument(
                source_key="demo",
                title="Unverified doc",
                doc_type=DocumentType.OTHER,
                url="https://example.gov.sa/unverified",
                verified=False,
            ),
        ],
    )

    assert [d.title for d in store.query(verified=True)] == ["Verified doc"]
    assert [d.title for d in store.query(verified=False)] == ["Unverified doc"]
    assert len(store.query()) == 2
