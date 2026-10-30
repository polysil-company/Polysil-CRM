"""Complaints (FS-015): the rules that need no database.

Working time, the complaint number, what an uploaded file really is, and the
date and line checks. Stand-in numbers are GAP entries; each is a constant here so
a setting can replace it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

IST: Final = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Rule 9: Monday to Saturday, 09:30 to 18:30 IST, no holidays (stand-ins, GAP-147).
WORK_START: Final = dt.time(9, 30)
WORK_END: Final = dt.time(18, 30)
WORK_DAYS: Final = frozenset(range(6))            # Monday 0 .. Saturday 5

MAX_LINES: Final = 20
MAX_ATTACHMENTS: Final = 10
MAX_UPLOAD_BYTES: Final = 10 * 1024 * 1024
CONTACT_NAME_MAX: Final = 120
TEXT_MAX: Final = 2000
FREQUENCY_MAX: Final = 200


# ── working time ─────────────────────────────────────────────────────────────

# A run of holidays must end the scan (FS-028 plan review B-2). The bound is on
# consecutive non-working days, not the whole target, so a long policy still
# computes (code review F-1); the SQL twin in migration 048 raises identically.
HORIZON_DAYS = 400


def _next_open(at: dt.datetime, holidays: frozenset[dt.date]) -> dt.datetime:
    """The first working instant at or after `at`, in IST, skipping holidays."""
    t = at.astimezone(IST)
    skipped = 0
    while True:
        start = dt.datetime.combine(t.date(), WORK_START, tzinfo=IST)
        end = dt.datetime.combine(t.date(), WORK_END, tzinfo=IST)
        if t.weekday() in WORK_DAYS and t.date() not in holidays and t < end:
            return max(t, start)
        skipped += 1
        if skipped > HORIZON_DAYS:
            raise ValueError(f"no working day within {HORIZON_DAYS} days")
        t = dt.datetime.combine(t.date() + dt.timedelta(days=1), WORK_START, tzinfo=IST)


def add_working_hours(start: dt.datetime, hours: int,
                      holidays: frozenset[dt.date] = frozenset()) -> dt.datetime:
    """`start` plus `hours` of working time. A start outside hours counts from the
    next opening; a target that lands exactly on closing time stays there. A
    holiday counts like a Sunday (FS-028); the caller passes the days, so the
    domain stays pure."""
    if start.tzinfo is None:
        raise ValueError("start must carry a timezone")
    remaining = dt.timedelta(hours=hours)
    t = _next_open(start, holidays)
    while True:
        end = dt.datetime.combine(t.date(), WORK_END, tzinfo=IST)
        if t + remaining <= end:
            return t + remaining
        remaining -= end - t
        t = _next_open(end, holidays)


def due_at(start: dt.datetime, hours: int | None, business_hours_only: bool,
           holidays: frozenset[dt.date] = frozenset()) -> dt.datetime | None:
    """A target from its policy row, or None when no row applied (EC-11)."""
    if hours is None:
        return None
    if business_hours_only:
        return add_working_hours(start, hours, holidays)
    return start + dt.timedelta(hours=hours)


def breached(due: dt.datetime | None, met: dt.datetime | None, now: dt.datetime) -> bool:
    """Computed on read: met after its target, or past its target and not met. A
    late response stays a breach once it is given, or the report would forgive it."""
    if due is None:
        return False
    return met > due if met is not None else now > due


# ── the number ───────────────────────────────────────────────────────────────

def complaint_no(fy: str, state_code: str, n: int) -> str:
    """`Poly/Comp./2026-27/GJ/01`: two digits at least, more as needed (rule 5)."""
    if n < 1:
        raise ValueError("a complaint number starts at 1")
    return f"Poly/Comp./{fy}/{state_code}/{n:02d}"


# ── files ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Sniffed:
    content_type: str
    extension: str
    inline: bool          # a browser shows it; HEIC is a download (EC-7)


_HEIC_BRANDS: Final = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


def sniff(head: bytes) -> Sniffed | None:
    """What the bytes are, whatever the client declared (EC-7). None: not allowed."""
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("image/jpeg", "jpg", True)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("image/png", "png", True)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Sniffed("image/webp", "webp", True)
    if head.startswith(b"%PDF-"):
        return Sniffed("application/pdf", "pdf", True)
    if head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return Sniffed("image/heic", "heic", False)
    return None


# ── the form ─────────────────────────────────────────────────────────────────

def ist_today(now: dt.datetime) -> dt.date:
    return now.astimezone(IST).date()


def date_problems(*, today: dt.date, supply_date: dt.date | None = None,
                  sample_courier_date: dt.date | None = None,
                  sample_received_on: dt.date | None = None, tested_on: dt.date | None = None,
                  field_visit_on: dt.date | None = None) -> dict[str, str]:
    """Rule 2: nothing after today in IST; the courier and the receipt not before
    the supply; the test not before the receipt (EC-15)."""
    out: dict[str, str] = {}
    named = {"supply_date": supply_date, "sample_courier_date": sample_courier_date,
             "sample_received_on": sample_received_on, "tested_on": tested_on,
             "field_visit_on": field_visit_on}
    for field, value in named.items():
        if value is not None and value > today:
            out[field] = "cannot be after today"
    if supply_date is not None:
        for field in ("sample_courier_date", "sample_received_on"):
            value = named[field]
            if value is not None and value < supply_date and field not in out:
                out[field] = "cannot be before the supply date"
    if (tested_on is not None and sample_received_on is not None
            and tested_on < sample_received_on and "tested_on" not in out):
        out["tested_on"] = "cannot be before the sample was received"
    return out


@dataclass(frozen=True)
class Line:
    product_id: str
    supplied_qty: Decimal
    defective_qty: Decimal


def line_problems(lines: list[Line]) -> dict[str, str]:
    """Rule 1 for a draft: 1 to 20 lines, one per product, defective within supplied."""
    out: dict[str, str] = {}
    if not 1 <= len(lines) <= MAX_LINES:
        out["lines"] = f"1 to {MAX_LINES} products"
    seen: set[str] = set()
    for i, line in enumerate(lines):
        if line.product_id in seen:
            out[f"lines[{i}].product_id"] = "each product once"
        seen.add(line.product_id)
        if line.supplied_qty <= 0:
            out[f"lines[{i}].supplied_qty"] = "more than zero"
        if line.defective_qty < 0:
            out[f"lines[{i}].defective_qty"] = "zero or more"
        elif line.defective_qty > line.supplied_qty:
            out[f"lines[{i}].defective_qty"] = "not more than supplied"
    return out


def nothing_defective(lines: list[Line]) -> bool:
    """To submit, at least one line has a defective quantity (rule 1, a guessed
    rule, GAP-148)."""
    return not any(line.defective_qty > 0 for line in lines)


def clean_text(value: str | None) -> str | None:
    """Trimmed; empty is absent (rule 2)."""
    if value is None:
        return None
    value = value.strip()
    return value or None
