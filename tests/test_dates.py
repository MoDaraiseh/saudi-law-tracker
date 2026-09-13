from __future__ import annotations

from datetime import date

from saudi_law_tracker.utils.dates import parse_hijri_date
from saudi_law_tracker.utils.text import normalize_for_match, slugify


def test_parse_hijri_from_arabic_digits():
    hijri, greg = parse_hijri_date("صدر بتاريخ ١٤٤٥/٠٣/١٥ هـ")
    assert hijri == "1445-03-15"
    assert isinstance(greg, date) and greg.year == 2023


def test_parse_gregorian_passthrough():
    hijri, greg = parse_hijri_date("Published 05/02/2024")
    assert hijri is None
    assert greg == date(2024, 2, 5)


def test_arabic_normalization():
    assert normalize_for_match("الأنظمة") == normalize_for_match("الانظمة")
    assert slugify("نظام العمل")
