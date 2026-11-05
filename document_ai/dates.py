"""Date parsing for the formats the synthetic documents emit."""

from __future__ import annotations

import re
from datetime import date

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTH_ABBR = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
MONTH_FULL = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

MIN_YEAR = 1990
MAX_YEAR = 2100


def format_date(value: date, style: str) -> str:
    if style == "iso":
        return value.isoformat()
    if style == "dmy_dot":
        return f"{value.day:02d}.{value.month:02d}.{value.year}"
    if style == "dmy_mon":
        return f"{value.day:02d} {MONTH_ABBR[value.month]} {value.year}"
    if style == "long":
        return f"{value.day} {MONTH_FULL[value.month]} {value.year}"
    raise ValueError(f"unknown date style: {style}")


def parse_date(value: str) -> date:
    raw = " ".join(value.strip().split())
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    dotted = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if dotted:
        return date(int(dotted.group(3)), int(dotted.group(2)), int(dotted.group(1)))
    named = re.fullmatch(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", raw)
    if named:
        month = MONTHS.get(named.group(2).lower())
        if month is None:
            raise ValueError(f"unrecognized date: {value}")
        return date(int(named.group(3)), month, int(named.group(1)))
    raise ValueError(f"unrecognized date: {value}")


def year_is_sane(value: date) -> bool:
    return MIN_YEAR <= value.year <= MAX_YEAR
