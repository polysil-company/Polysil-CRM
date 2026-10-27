"""Reports to PDF (FS-077): the report's own rows on an A4 landscape page.

The page is built from the same JSON and the same column specs as the Excel and
CSV files, so it carries the same scope, filters and blanks. Every cell goes
through `exports.cell_value()` first, then a formatter: a hidden figure is an empty
cell, a real 0 prints 0 (ADR-047, EC-1).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from api.config import get_settings
from api.errors import ServiceUnavailableError
from api.pdf import (
    BUSY,
    env,
    logo,
    logo_only_fetcher,
    render_limited,
    renderer_available,
    slot_free,
)
from api.services import exports, report_exports
from api.services.exports import IST, Column

# the controls that flip the reading order of the rest of a cell (EC-22)
_BIDI: Final = re.compile("[‪-‮⁦-⁩]")
NUMBER_KINDS: Final = frozenset({"int", "money", "decimal"})
WIDE: Final = 12                      # columns above which the font shrinks (EC-8)
# the reports whose figures depend on when a sale counts (FS-026, EC-10)
_SALE_MODE: Final = frozenset({"salesperson-performance", "dealer-performance",
                               "campaign-performance", "territory-performance"})
_MODE_TEXT: Final = {"submission": "sales counted when the order is submitted",
                     "approval": "sales counted when the order is approved",
                     "dispatch": "sales counted when the order is dispatched",
                     "payment": "sales counted when the order is paid"}
TITLES: Final = {"sales-forecast": "Sales forecast", "insights": "Insights",
                 "lead-conversion": "Lead conversion",
                 "salesperson-performance": "Salesperson performance",
                 "lost-leads": "Lost leads", "follow-ups": "Follow-ups",
                 "dealer-performance": "Dealer performance",
                 "territory-performance": "Territory performance", "complaints": "Complaints",
                 "campaign-performance": "Campaign performance"}


@dataclass(frozen=True)
class Page:
    title: str
    columns: Sequence[Column]
    rows: Sequence[dict[str, Any]]
    total: dict[str, Any] | None
    notes: Sequence[str]
    filter_line: str


# ── formatting ───────────────────────────────────────────────────────────────

def inr(value: Decimal) -> str:
    """`₹1,05,000.00`: Indian grouping; `-₹50.00` (GAP-543)."""
    q = value.quantize(Decimal("0.01"))
    if q == 0:
        q = abs(q)
    sign = "-" if q < 0 else ""
    whole, _, paise = format(abs(q), "f").partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{paise}"


def when(value: dt.datetime) -> str:
    """`25 Oct 2026, 2:30 pm`, built without `%-I` so it runs on Windows (EC-23)."""
    hour = value.hour % 12 or 12
    half = "am" if value.hour < 12 else "pm"
    return f"{value.day} {value:%b %Y}, {hour}:{value:%M} {half}"


def day(value: dt.date) -> str:
    return f"{value.day} {value:%b %Y}"


def cell(raw: Any, kind: exports.Kind) -> str:
    """One cell. None is empty (a figure the reader may not see); 0 prints 0."""
    value = exports.cell_value(raw, kind)
    if value is None:
        return ""
    if isinstance(value, str):
        return _BIDI.sub("", value)
    if isinstance(value, Decimal):
        return inr(value) if kind == "money" else exports.decimal_text(value)
    if isinstance(value, dt.datetime):
        return when(value)
    if isinstance(value, dt.date):
        return day(value)
    return str(value)


def _get(item: dict[str, Any], path: str) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _ist(iso: str | None) -> dt.datetime | None:
    if not iso:
        return None
    try:
        parsed = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(IST)


def _date(iso: str | None) -> str | None:
    try:
        return day(dt.date.fromisoformat(str(iso)[:10])) if iso else None
    except ValueError:
        return None


# ── the filter line, one builder per report shape (EC-10) ────────────────────

def report_filter_line(report: str, data: dict[str, Any]) -> str:
    f = data.get("filters") or {}
    parts: list[str] = []
    if report == "follow-ups":
        as_of = _ist(f.get("as_of"))
        if as_of:
            parts.append(f"As of {when(as_of)}")
    elif report == "sales-forecast":
        if f.get("history_days"):
            parts.append(f"Win rates from leads closed in the last {f['history_days']} days")
        on = _date(f.get("as_of"))
        if on:
            parts.append(f"as of {on}")
    else:
        start, end = _date(f.get("from")), _date(f.get("to"))
        if start and end:
            parts.append(f"From {start} to {end}")
    territories = f.get("territory_id")
    if territories:
        n = len(territories) if isinstance(territories, list) else 1
        parts.append("1 territory" if n == 1 else f"{n} territories")
    if f.get("owner_id"):
        parts.append("one person")
    if report in _SALE_MODE and f.get("sale_counted_at") in _MODE_TEXT:
        parts.append(_MODE_TEXT[str(f["sale_counted_at"])])
    if data.get("group_by"):
        parts.append(f"by {str(data['group_by']).replace('_', ' ')}")
    return " · ".join(parts)


def list_filter_line(filters: dict[str, Any]) -> str:
    """The subsidy reports' own filters: status, stage, search."""
    parts: list[str] = []
    for key, label in (("status", "Status"), ("stage", "Stage"), ("district", "District"),
                       ("q", "Search")):
        value = filters.get(key)
        if value not in (None, "", [], False):
            parts.append(f"{label}: {value}")
    return " · ".join(parts)


# ── notes (EC-7, EC-21, EC-28) ───────────────────────────────────────────────

def note_text(note: dict[str, Any]) -> str:
    kind = note.get("kind")
    if kind == "refunds":
        count = note.get("count")
        amount = note.get("amount")
        money = inr(Decimal(str(amount))) if amount not in (None, "") else ""
        return f"Refunds paid: {'' if count is None else count}, amount {money}".rstrip()
    if kind == "partial_totals":
        return "Totals are given for " + ", ".join(note.get("columns") or []) + " only."
    if kind == "truncated":
        n = note.get("row_count")
        if n:
            return f"Totals cover all {n:,} rows; the table shows the first 1,000."
        return "The table shows the first 1,000 rows; totals cover them all."
    return ""


def report_page(report: str, data: dict[str, Any]) -> Page:
    cols = report_exports.columns(report, data)
    total, _ = report_exports.total_row(report, data)
    return Page(title=TITLES.get(report, report.replace("-", " ").capitalize()), columns=cols,
                rows=list(data.get("rows") or []), total=total or None,
                notes=[t for t in (note_text(n) for n in report_exports.notes(report, data)) if t],
                filter_line=report_filter_line(report, data))


# ── rendering ────────────────────────────────────────────────────────────────

def html(page: Page, made_by: str | None, now: dt.datetime | None = None) -> str:
    stamp = when((now or dt.datetime.now(IST)).astimezone(IST))
    made = f"Made by {made_by} on {stamp}" if made_by else f"Made on {stamp}"
    headers = [{"text": c.header, "number": c.kind in NUMBER_KINDS} for c in page.columns]
    rows = [[cell(_get(r, c.path), c.kind) for c in page.columns] for r in page.rows]
    total = ([cell(_get(page.total, c.path), c.kind) for c in page.columns]
             if page.total is not None else None)
    return env.get_template("report.html").render(
        title=page.title, filter_line=page.filter_line, headers=headers, rows=rows, total=total,
        notes=list(page.notes), made=made, logo=logo(), wide=len(page.columns) > WIDE)


async def caller_name(db: Any) -> str | None:
    """The caller's own name for the footer. A caller can always read their own
    app_user row (FS-003 4); people_names() covers only people on visible records."""
    from sqlalchemy import text

    name = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
    ).scalar_one_or_none()
    return str(name) if name else None


def html_mode() -> bool:
    return get_settings().pdf_renderer == "html"


def check_ready() -> None:
    """Before the queries a refused request would waste (EC-9). Best effort: the
    render thread decides (plan review S-2)."""
    if html_mode():
        return
    if renderer_available():
        raise ServiceUnavailableError("PDFs cannot be made right now.", code="pdf_unavailable")
    if not slot_free():
        raise ServiceUnavailableError(BUSY, code="busy")


async def render(page_html: str) -> tuple[bytes, str, str]:
    """(body, content type, extension). In the `html` renderer mode the page itself,
    labelled as HTML (EC-15)."""
    if html_mode():
        return page_html.encode("utf-8"), "text/html; charset=utf-8", "html"
    if renderer_available():
        raise ServiceUnavailableError("PDFs cannot be made right now.", code="pdf_unavailable")
    body = await asyncio.to_thread(render_limited, page_html, logo_only_fetcher)
    return body, exports.PDF_TYPE, "pdf"
