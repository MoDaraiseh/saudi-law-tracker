"""Arabic-aware text cleanup and hashing helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_TATWEEL = "ـ"
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٟۖ-ۜ۟-۪ۨ-ۭ]")
_WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(_TATWEEL, "")
    return _WS.sub(" ", text).strip()


def normalize_for_match(text: str) -> str:
    """Aggressive normalization for dedupe/comparison, not for display."""

    text = clean(text)
    text = _DIACRITICS.sub("", text)
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(src, dst)
    return text.lower()


def slugify(text: str, max_len: int = 60) -> str:
    text = normalize_for_match(text)
    text = re.sub(r"[^\w؀-ۿ]+", "-", text).strip("-")
    return text[:max_len] or "item"


def content_hash(*parts: str | None) -> str:
    joined = "␟".join(normalize_for_match(p or "") for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
