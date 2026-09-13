"""Hijri <-> Gregorian helpers. Saudi sources publish dates in Hijri."""

from __future__ import annotations

import re
from datetime import date

from hijridate.convert import Gregorian, Hijri

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# Three /-, - or .-separated numbers, in either day/month/year or year/month/day
# order (Saudi sources use both). The year is whichever outer group is >= 100.
_DATE_RE = re.compile(r"(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})")


def normalize_digits(text: str) -> str:
    return text.translate(_AR_DIGITS)


def hijri_to_gregorian(year: int, month: int, day: int) -> date | None:
    try:
        g = Hijri(year, month, day).to_gregorian()
        return date(g.year, g.month, g.day)
    except (ValueError, OverflowError):
        return None


def gregorian_to_hijri_str(d: date) -> str:
    h = Gregorian(d.year, d.month, d.day).to_hijri()
    return f"{h.year:04d}-{h.month:02d}-{h.day:02d}"


def parse_hijri_date(text: str) -> tuple[str | None, date | None]:
    """Extract a day/month/year date from free text, either digit order.

    Returns (hijri_string, gregorian_date). A year < 1600 is treated as Hijri,
    so the Gregorian date is converted; otherwise the date is already Gregorian
    and the Hijri string is left as None.
    """

    m = _DATE_RE.search(normalize_digits(text))
    if not m:
        return None, None
    first, month, last = (int(x) for x in m.groups())
    if first >= 100:  # year/month/day
        year, day = first, last
    elif last >= 100:  # day/month/year
        year, day = last, first
    else:
        return None, None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None, None

    if year < 1600:  # Hijri
        return f"{year:04d}-{month:02d}-{day:02d}", hijri_to_gregorian(year, month, day)
    try:
        return None, date(year, month, day)
    except ValueError:
        return None, None
