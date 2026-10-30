"""FS-077: the report PDF's page and the shared render limit. No database, no
WeasyPrint: the html is checked as text, the limit with a stand-in render."""

# ruff: noqa: E501  (inline cases; the full-width signs are the test)

from __future__ import annotations

import asyncio
import datetime as dt
import threading
from decimal import Decimal

import pytest

from api import pdf
from api.errors import ServiceUnavailableError
from api.services import report_pdf
from api.services.report_pdf import cell, inr, note_text, when

SALES = {"rows": [{"user": {"id": "u1", "full_name": "Ravi <b>Patel</b>"}, "leads_created": 3,
                   "leads_won": 1, "quotations_sent": 2, "orders": None, "order_value": "105000.00",
                   "visits": 0, "tasks_done": None, "tasks_overdue": None}],
         "truncated": False, "row_count": 1,
         "filters": {"from": "2026-10-01", "to": "2026-10-25", "territory_id": ["t1", "t2"],
                     "owner_id": None, "sale_counted_at": "approval"},
         "totals": {"leads_created": 3, "leads_won": 1}}


@pytest.mark.parametrize(("value", "expected"), [
    ("105000", "₹1,05,000.00"), ("1234567.5", "₹12,34,567.50"), ("999", "₹999.00"),
    ("1000", "₹1,000.00"), ("-50", "-₹50.00"), ("-0.004", "₹0.00"), ("0", "₹0.00"),
    ("100000000", "₹10,00,00,000.00"),
])
def test_inr_uses_indian_grouping(value: str, expected: str) -> None:
    """GAP-543: Indian grouping and `-₹50.00` until the client says otherwise."""
    assert inr(Decimal(value)) == expected


@pytest.mark.parametrize(("hour", "minute", "expected"), [
    (14, 30, "25 Oct 2026, 2:30 pm"), (0, 5, "25 Oct 2026, 12:05 am"), (12, 0, "25 Oct 2026, 12:00 pm"),
    (9, 7, "25 Oct 2026, 9:07 am"),
])
def test_when_needs_no_platform_specific_format(hour: int, minute: int, expected: str) -> None:
    """EC-23: no `%-I`, which fails on Windows."""
    assert when(dt.datetime(2026, 10, 25, hour, minute)) == expected


def test_a_hidden_figure_is_blank_and_zero_is_zero() -> None:
    """EC-1, ADR-047."""
    assert cell(None, "int") == "" and cell(0, "int") == "0"
    assert cell(None, "money") == "" and cell("0", "money") == "₹0.00"
    assert cell(False, "bool") == "No" and cell(True, "bool") == "Yes"
    assert cell("2026-10-25T09:00:00+00:00", "datetime") == "25 Oct 2026, 2:30 pm"


def test_bidi_controls_are_stripped() -> None:
    """EC-22."""
    assert cell("abc‮def", "text") == "abcdef"


def test_the_page_holds_title_filters_headers_rows_total_and_escapes_names() -> None:
    page = report_pdf.report_page("salesperson-performance", SALES)
    html = report_pdf.html(page, "Asha <script>", now=dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.UTC))
    assert "Salesperson performance" in html
    assert "From 1 Oct 2026 to 25 Oct 2026 · 2 territories · sales counted when the order is approved" in html
    assert "<th>Person</th>" in html and ">Visits</th>" in html
    assert "Ravi &lt;b&gt;Patel&lt;/b&gt;" in html and "<b>Patel" not in html
    assert "Made by Asha &lt;script&gt; on 25 Oct 2026, 2:30 pm" in html
    assert "₹1,05,000.00" in html
    assert "None" not in html, "a hidden figure is never the text None (EC-1)"
    assert '<td class="n">0</td>' in html, "a real 0 prints 0 (EC-1)"
    assert "Totals are given for Leads created, Leads won only." in html, "EC-28"


def test_follow_ups_say_as_of_in_ist_and_no_window() -> None:
    """EC-10."""
    line = report_pdf.report_filter_line("follow-ups", {"filters": {"as_of": "2026-10-25T18:40:00+00:00"}})
    assert line == "As of 26 Oct 2026, 12:10 am"


def test_the_sale_mode_shows_only_where_it_matters() -> None:
    f = {"filters": {"from": "2026-10-01", "to": "2026-10-25", "sale_counted_at": "approval"}}
    assert "sales counted" not in report_pdf.report_filter_line("lost-leads", f)
    assert "sales counted" in report_pdf.report_filter_line("dealer-performance", f)


def test_notes() -> None:
    assert note_text({"kind": "truncated", "row_count": 1450}) == \
        "Totals cover all 1,450 rows; the table shows the first 1,000."
    assert note_text({"kind": "refunds", "count": 3, "amount": "105000.00"}) == \
        "Refunds paid: 3, amount ₹1,05,000.00"
    assert note_text({"kind": "partial_totals", "columns": ["Leads"]}) == "Totals are given for Leads only."


def test_a_truncated_report_says_what_the_totals_cover() -> None:
    """EC-7."""
    page = report_pdf.report_page("salesperson-performance", {**SALES, "truncated": True, "row_count": 1450})
    assert "Totals cover all 1,450 rows; the table shows the first 1,000." in page.notes


def test_a_wide_report_gets_the_smaller_font() -> None:
    data = {"rows": [], "totals": {}, "filters": {}, "truncated": False}
    page = report_pdf.report_page("campaign-performance", data)
    assert len(page.columns) > report_pdf.WIDE
    assert "font-size: 7pt" in report_pdf.html(page, None)


def test_the_list_filter_line() -> None:
    assert report_pdf.list_filter_line({"status": "open", "stage": None, "q": "123"}) == "Status: open · Search: 123"


# ── the render limit (EC-2, plan review S-1) ─────────────────────────────────

def test_a_third_render_is_busy_and_slots_come_back(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    monkeypatch.setattr(pdf, "render_pdf", lambda html, fetcher=None: (gate.wait(5), b"%PDF")[1])

    async def run() -> None:
        first = asyncio.create_task(asyncio.to_thread(pdf.render_limited, "a"))
        second = asyncio.create_task(asyncio.to_thread(pdf.render_limited, "b"))
        await asyncio.sleep(0.2)
        assert not pdf.slot_free()
        with pytest.raises(ServiceUnavailableError) as busy:
            await asyncio.to_thread(pdf.render_limited, "c")
        assert busy.value.code == "busy"
        gate.set()
        assert await first == b"%PDF" and await second == b"%PDF"
        assert pdf.slot_free()

    asyncio.run(run())


def test_cancelling_the_request_does_not_free_the_slot_while_the_thread_renders(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-2: the old context manager freed its slot on cancellation."""
    gate = threading.Event()
    monkeypatch.setattr(pdf, "render_pdf", lambda html, fetcher=None: (gate.wait(5), b"%PDF")[1])

    async def run() -> None:
        tasks = [asyncio.create_task(asyncio.to_thread(pdf.render_limited, "x")) for _ in range(2)]
        await asyncio.sleep(0.2)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not pdf.slot_free(), "the threads still render, so the slots are still taken"
        with pytest.raises(ServiceUnavailableError):
            await asyncio.to_thread(pdf.render_limited, "y")
        gate.set()
        for _ in range(50):
            if pdf.slot_free():
                break
            await asyncio.sleep(0.05)
        assert pdf.slot_free(), "the threads give their slots back when they finish"

    asyncio.run(run())


def test_a_refused_render_never_builds_the_fetcher() -> None:
    """Building the fetcher imports WeasyPrint; a busy refusal must not pay for it
    (found by the full suite on a box without WeasyPrint's libraries)."""
    built: list[int] = []
    taken = 0
    while pdf.slots.acquire(blocking=False):
        taken += 1
    try:
        with pytest.raises(ServiceUnavailableError):
            pdf.render_limited("x", lambda: built.append(1))
    finally:
        for _ in range(taken):
            pdf.slots.release()
    assert built == []
