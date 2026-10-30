"""Reports to Excel (FS-024 §11, closes GAP-220): the report's own rows, written by
the list exports' writer (FS-030).

The workbook is built from the JSON the report already answered, so it carries the
same scope, the same filters and the same nulls: a figure the caller may not see is
an empty cell, never 0 (ADR-047). Below the rows sit a Total line from the report's
`totals`, and a note when the report kept only its first 1,000 rows.
"""

from __future__ import annotations

from typing import Any, Final

from api.services.exports import Column

# the report name in the URL is the file stem's tail and the key here
NAMES: Final = ("sales-forecast", "insights",
                 "lead-conversion", "salesperson-performance", "lost-leads", "follow-ups",
                "dealer-performance", "territory-performance", "complaints",
                "campaign-performance")

_GROUP: Final = {"source": "Source", "owner": "Owner", "territory": "Territory",
                 "reason": "Lost reason", "type": "Complaint type", "status": "Status",
                 "severity": "Severity"}

# where a report's totals name a column differently from its rows
_TOTAL_KEY: Final = {("lost-leads", "count"): "lost"}

# a lost lead's last stage before it was lost (FS-024 rule 6)
_LOST_FROM: Final = ("new", "contacted", "qualified", "quoted", "negotiation", "unknown")


def columns(report: str, data: dict[str, Any]) -> tuple[Column, ...]:
    group = _GROUP.get(str(data.get("group_by")), "Group")
    if report == "lead-conversion":
        return (Column(group, "key.label"), Column("Leads", "leads", "int"),
                Column("Contacted", "contacted", "int"), Column("Qualified", "qualified", "int"),
                Column("Quoted", "quoted", "int"), Column("Won", "won", "int"),
                Column("Lost", "lost", "int"), Column("Open", "open", "int"),
                Column("Conversion %", "conversion_pct", "decimal"))
    if report == "lost-leads":
        return (Column(group, "key.label"), Column("Lost", "count", "int"),
                Column("Share %", "share_pct", "decimal"),
                Column("Average days to loss", "avg_days_to_loss", "decimal"),
                *(Column(f"Lost from {s}", f"by_stage.{s}", "int") for s in _LOST_FROM))
    if report == "salesperson-performance":
        return (Column("Person", "user.full_name"), Column("Leads created", "leads_created", "int"),
                Column("Leads won", "leads_won", "int"),
                Column("Quotations sent", "quotations_sent", "int"),
                Column("Orders", "orders", "int"), Column("Order value", "order_value", "money"),
                Column("Visits", "visits", "int"), Column("Tasks done", "tasks_done", "int"),
                Column("Tasks overdue", "tasks_overdue", "int"))
    if report == "follow-ups":
        return (Column("Person", "user.full_name"), Column("Due today", "due_today", "int"),
                Column("Overdue 1-2 days", "overdue_1_2", "int"),
                Column("Overdue 3-7 days", "overdue_3_7", "int"),
                Column("Overdue 8-30 days", "overdue_8_30", "int"),
                Column("Overdue 31+ days", "overdue_31_plus", "int"),
                Column("Oldest due", "oldest_due_at", "datetime"))
    if report == "dealer-performance":
        return (Column("Dealer", "partner.name"), Column("Orders", "orders", "int"),
                Column("Order value", "order_value", "money"),
                Column("Dispatched value", "dispatched_value", "money"),
                Column("Leads assigned", "leads_assigned", "int"),
                Column("Received", "received", "money"), Column("Balance", "balance", "money"),
                Column("Complaints", "complaints", "int"))
    if report == "territory-performance":
        return (Column("Territory", "territory.name"), Column("Leads", "leads", "int"),
                Column("Won", "won", "int"), Column("Conversion %", "conversion_pct", "decimal"),
                Column("Orders", "orders", "int"), Column("Order value", "order_value", "money"))
    if report == "complaints":
        return (Column(group, "key.label"), Column("Complaints", "count", "int"),
                Column("Resolved", "resolved", "int"),
                Column("Resolved within SLA %", "resolved_within_sla_pct", "decimal"),
                Column("Response breaches", "response_breaches", "int"))
    if report == "campaign-performance":
        return (Column("Campaign", "campaign.name"), Column("Type", "campaign.type"),
                Column("Starts", "campaign.start_date", "date"),
                Column("Ends", "campaign.end_date", "date"),
                Column("Leads", "leads", "int"), Column("Qualified", "qualified", "int"),
                Column("Won", "won", "int"), Column("Lost", "lost", "int"),
                Column("Open", "open", "int"), Column("Conversion %", "conversion_pct", "decimal"),
                Column("Sales", "sales_count", "int"),
                Column("Sales value", "sales_value", "money"),
                Column("Planned cost", "cost_planned", "money"),
                Column("Actual cost", "cost_actual", "money"), Column("Cost", "cost", "money"),
                Column("Cost per lead", "cost_per_lead", "money"),
                Column("Cost per win", "cost_per_won", "money"))
    if report == "sales-forecast":
        months = [*(data.get("months") or []), "later"]
        return (Column(group, "key.label"), Column("Open leads", "open", "int"),
                Column("With a value", "with_value", "int"),
                Column("Pipeline value", "pipeline_value", "money"),
                Column("Weighted value", "weighted_value", "money"),
                *(Column("Later" if m == "later" else m, f"by_month.{m}", "money") for m in months),
                Column("Valued by quotation", "valued_by.quotation", "int"),
                Column("Valued by estimate", "valued_by.estimate", "int"))
    if report == "insights":
        return (Column("Insight", "title"), Column("Figure", "figure", "decimal"),
                Column("Previous", "previous", "decimal"), Column("Unit", "unit"))
    raise ValueError(f"no columns for report {report!r}")


def _dig(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _has_key(row: dict[str, Any], path: str) -> bool:
    """Present, whatever the value: a hidden total is still a total (N-1)."""
    head, _, rest = path.partition(".")
    if head not in row:
        return False
    return _has_key(row[head], rest) if rest else True


def _put(row: dict[str, Any], path: str, value: Any) -> None:
    head, _, rest = path.partition(".")
    if rest:
        _put(row.setdefault(head, {}), rest, value)
    else:
        row[head] = value


# sentences, not figures: a Total line would be empty (code review F-5)
NO_TOTAL: Final = frozenset({"insights"})


def total_row(report: str, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The Total line, and the headers of the columns it totals. A column counts as
    totalled when its key is present, whatever the value: a hidden total is still a
    total the reader may not see (ADR-047, FS-077 plan review N-1)."""
    cols = columns(report, data)
    if report in NO_TOTAL:
        return {}, []
    totals = data.get("totals") or {}
    total: dict[str, Any] = {}
    _put(total, cols[0].path, "Total")
    totalled: list[str] = []
    for col in cols[1:]:
        key = _TOTAL_KEY.get((report, col.path), col.path)
        if _has_key(totals, key):
            _put(total, col.path, _dig(totals, key))
            totalled.append(col.header)
    return total, totalled


def notes(report: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """The notes under a report, as data, so each format writes them its own way
    (FS-077 EC-21). Kinds: refunds, truncated, partial_totals."""
    cols = columns(report, data)
    out: list[dict[str, Any]] = []
    refunds = (data.get("totals") or {}).get("refunds")
    if isinstance(refunds, dict):
        out.append({"kind": "refunds", "count": refunds.get("count"),
                    "amount": refunds.get("amount")})
    _, totalled = total_row(report, data)
    figures = [c.header for c in cols[1:] if c.kind in ("int", "money", "decimal")]
    if totalled and len(totalled) < len(figures):
        out.append({"kind": "partial_totals", "columns": totalled})
    if data.get("truncated"):
        out.append({"kind": "truncated", "row_count": data.get("row_count")})
    return out


def rows(report: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """The report's rows, then its Total line, then any notes, as rows the writer
    reads by the same column paths."""
    cols = columns(report, data)
    first = cols[0].path
    out: list[dict[str, Any]] = list(data.get("rows") or [])
    totals = data.get("totals") or {}
    total: dict[str, Any] = {}
    _put(total, first, "Total")
    for col in cols[1:]:
        key = _TOTAL_KEY.get((report, col.path), col.path)
        if _has_key(totals, key):
            _put(total, col.path, _dig(totals, key))
    if report not in NO_TOTAL:
        out.append(total)
    refunds = totals.get("refunds")
    if isinstance(refunds, dict):
        note: dict[str, Any] = {}
        _put(note, first, f"Refunds paid: {refunds.get('count', 0)}, "
                          f"amount {refunds.get('amount', '0.00')}")
        out.append(note)
    if data.get("truncated"):
        note = {}
        _put(note, first, "Only the first 1,000 rows. Narrow the filters to see the rest.")
        out.append(note)
    return out
