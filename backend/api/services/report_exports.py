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
NAMES: Final = ("lead-conversion", "salesperson-performance", "lost-leads", "follow-ups",
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
    raise ValueError(f"no columns for report {report!r}")


def _put(row: dict[str, Any], path: str, value: Any) -> None:
    head, _, rest = path.partition(".")
    if rest:
        _put(row.setdefault(head, {}), rest, value)
    else:
        row[head] = value


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
        if key in totals:
            total[col.path] = totals[key]
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
