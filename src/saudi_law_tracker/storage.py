"""Persistence: a local SQLite store with diffing, plus raw HTML snapshots."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .models import RegulatoryDocument

# Column order matches RegulatoryDocument's fields; list-valued fields are stored
# as JSON text, dates/datetimes as ISO strings.
_COLUMNS: tuple[str, ...] = (
    "uid",
    "source_key",
    "title",
    "title_en",
    "doc_type",
    "url",
    "pdf_urls",
    "reference_number",
    "summary",
    "published_gregorian",
    "published_hijri",
    "effective_date",
    "last_modified",
    "categories",
    "raw_html_path",
    "content_hash",
    "first_seen",
    "last_seen",
    "verified",
)
_JSON_COLUMNS = ("pdf_urls", "categories")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS regulations (
    uid                 TEXT PRIMARY KEY,
    source_key          TEXT NOT NULL,
    title               TEXT NOT NULL,
    title_en            TEXT,
    doc_type            TEXT NOT NULL,
    url                 TEXT NOT NULL,
    pdf_urls            TEXT NOT NULL DEFAULT '[]',
    reference_number    TEXT,
    summary             TEXT,
    published_gregorian TEXT,
    published_hijri     TEXT,
    effective_date      TEXT,
    last_modified       TEXT,
    categories          TEXT NOT NULL DEFAULT '[]',
    raw_html_path       TEXT,
    content_hash        TEXT,
    first_seen          TEXT NOT NULL,
    last_seen           TEXT NOT NULL,
    verified            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_regulations_source ON regulations (source_key);
CREATE INDEX IF NOT EXISTS ix_regulations_published
    ON regulations (source_key, published_gregorian);
"""


class DocumentStore:
    """SQLite-backed store, one ``regulations`` table keyed by document uid.

    A document's uid is derived from its source, URL and publication date, so
    `upsert_many` reports an entry as *new* only when that combination has not
    been stored before, and as *updated* when it has but the content hash
    differs. A plain re-scrape of an unchanged page is neither.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.path = settings.db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after a database's initial creation."""

        existing = {row["name"] for row in conn.execute("PRAGMA table_info(regulations)")}
        if "verified" not in existing:
            conn.execute(
                "ALTER TABLE regulations ADD COLUMN verified INTEGER NOT NULL DEFAULT 0"
            )
        if "last_modified" not in existing:
            conn.execute("ALTER TABLE regulations ADD COLUMN last_modified TEXT")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _to_row(doc: RegulatoryDocument) -> dict[str, Any]:
        data = doc.model_dump(mode="json")
        for col in _JSON_COLUMNS:
            data[col] = json.dumps(data[col], ensure_ascii=False)
        return {col: data[col] for col in _COLUMNS}

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RegulatoryDocument:
        data = dict(row)
        for col in _JSON_COLUMNS:
            data[col] = json.loads(data[col])
        return RegulatoryDocument.model_validate(data)

    def load(self, source_key: str) -> dict[str, RegulatoryDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM regulations WHERE source_key = ? "
                "ORDER BY published_gregorian IS NULL, published_gregorian",
                (source_key,),
            ).fetchall()
        return {row["uid"]: self._from_row(row) for row in rows}

    def count(self, source_key: str) -> int:
        with self._connect() as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM regulations WHERE source_key = ?", (source_key,)
            ).fetchone()
        return int(n)

    def query(
        self,
        *,
        sources: list[str] | None = None,
        doc_types: list[str] | None = None,
        sector: str | None = None,
        text: str | None = None,
        since: date | None = None,
        until: date | None = None,
        verified: bool | None = None,
        limit: int | None = None,
    ) -> list[RegulatoryDocument]:
        """Filtered read across every source, newest publication first.

        ``sector`` is matched as a substring of the source key or the stored
        categories, so ``"labor"`` finds the ``mhrsd_labor`` source and the
        ``labor_law_amendment`` category. ``text`` matches title or summary.
        Date bounds compare against ``published_gregorian`` and exclude rows
        with no Gregorian date. ``verified`` filters on the ``verified``
        column; leave it ``None`` to return both verified and unverified rows.
        """

        where: list[str] = []
        params: list[Any] = []
        if sources:
            where.append(f"source_key IN ({', '.join('?' for _ in sources)})")
            params.extend(sources)
        if doc_types:
            where.append(f"doc_type IN ({', '.join('?' for _ in doc_types)})")
            params.extend(doc_types)
        if sector:
            where.append("(source_key LIKE ? OR categories LIKE ?)")
            params += [f"%{sector}%", f"%{sector}%"]
        if text:
            where.append("(title LIKE ? OR IFNULL(summary, '') LIKE ?)")
            params += [f"%{text}%", f"%{text}%"]
        if since is not None:
            where.append("published_gregorian >= ?")
            params.append(since.isoformat())
        if until is not None:
            where.append("published_gregorian <= ?")
            params.append(until.isoformat())
        if verified is not None:
            where.append("verified = ?")
            params.append(int(verified))

        sql = "SELECT * FROM regulations"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY published_gregorian IS NULL, published_gregorian DESC, first_seen DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_row(row) for row in rows]

    def upsert_many(
        self, source_key: str, incoming: list[RegulatoryDocument]
    ) -> tuple[list[str], list[str]]:
        """Merge scraped documents into the store.

        Returns ``(new_uids, updated_uids)``: uids not seen before, and uids
        whose stored content hash changed. Unchanged re-scrapes only bump
        ``last_seen`` and appear in neither list.
        """

        now = datetime.now(UTC).isoformat()
        new_uids: list[str] = []
        updated_uids: list[str] = []

        insert_cols = ", ".join(_COLUMNS)
        insert_ph = ", ".join(f":{c}" for c in _COLUMNS)
        update_set = ", ".join(
            f"{c} = :{c}" for c in _COLUMNS if c not in ("uid", "first_seen")
        )

        with self._connect() as conn:
            known: dict[str, str | None] = {
                row["uid"]: row["content_hash"]
                for row in conn.execute(
                    "SELECT uid, content_hash FROM regulations WHERE source_key = ?",
                    (source_key,),
                )
            }
            for doc in incoming:
                row = self._to_row(doc)
                if doc.uid not in known:
                    row["first_seen"] = row["last_seen"] = now
                    conn.execute(
                        f"INSERT INTO regulations ({insert_cols}) VALUES ({insert_ph})", row
                    )
                    new_uids.append(doc.uid)
                elif known[doc.uid] != doc.content_hash:
                    row["last_seen"] = now  # first_seen is preserved by the SET list
                    conn.execute(
                        f"UPDATE regulations SET {update_set} WHERE uid = :uid", row
                    )
                    updated_uids.append(doc.uid)
                else:
                    conn.execute(
                        "UPDATE regulations SET last_seen = ? WHERE uid = ?", (now, doc.uid)
                    )

        return new_uids, updated_uids

    def write_raw(self, source_key: str, slug: str, content: bytes | str) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self.settings.raw_dir / source_key / f"{stamp}__{slug}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        return target


class RunState:
    """Small JSON file per source tracking the last successful run."""

    def __init__(self, settings: Settings) -> None:
        self.path = settings.state_dir / "runs.json"
        settings.ensure_dirs()

    def _read(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        data: dict[str, dict[str, str]] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def get(self, source_key: str) -> dict[str, str]:
        return self._read().get(source_key, {})

    def mark(self, source_key: str, *, ok: bool, detail: str = "") -> None:
        data = self._read()
        data[source_key] = {
            "last_run": datetime.now(UTC).isoformat(),
            "status": "ok" if ok else "error",
            "detail": detail,
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
