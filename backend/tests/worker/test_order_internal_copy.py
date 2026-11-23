"""FS-091: the order PDF's internal copy carries every approval round, who decided
and their remarks; the customer copy carries none of it. Mode `internal` renders
only the internal copy and leaves the customer copy alone. No database: the claim
and the lease are in tests/db/test_migration_092.py."""

from __future__ import annotations

import asyncio
import io
import re
from typing import Any

import pytest

import worker.jobs.orders as job
from api.config import get_settings
from api.domain.orders import internal_pdf_storage_key, pdf_filename, pdf_storage_key
from tests.worker.test_order_render import _doc
from tests.worker.test_quotation_render import (
    _text,
    assert_every_glyph_on_the_page,
    needs_weasyprint,
)
from worker.jobs.quotations import render_pdf

RETURNED = "Rate below the district floor. Re-quote at ₹1,650."
APPROVED_DM = "OK at the revised rate."
ESCALATED = "Approved in place of the State Manager, who is on leave."


def _internal(**extra: Any) -> dict[str, Any]:
    return {
        "remarks": "Deliver before the sowing window.",
        "amend_reason": None, "amend_count": 0,
        "approvals": [
            {"round": 1, "status": "rejected", "amount": "185000.00",
             "requested_at": "2026-11-20T04:32:00+00:00", "requested_by": "Kiran Officer",
             "request_remark": None, "decided_at": "2026-11-20T07:10:00+00:00",
             "steps": [
                 {"seq": 1, "role": "District Manager", "decided_role": None,
                  "decision": "reject", "by": "Dilip Manager",
                  "decided_at": "2026-11-20T07:10:00+00:00", "remark": RETURNED},
                 {"seq": 2, "role": "State Manager", "decided_role": None,
                  "decision": None, "by": None, "decided_at": None, "remark": None},
             ]},
            {"round": 2, "status": "approved", "amount": "166750.00",
             "requested_at": "2026-11-21T03:00:00+00:00", "requested_by": "Kiran Officer",
             "request_remark": "Re-quoted as asked.", "decided_at": "2026-11-21T09:45:00+00:00",
             "steps": [
                 {"seq": 1, "role": "District Manager", "decided_role": None,
                  "decision": "approve", "by": "Dilip Manager",
                  "decided_at": "2026-11-21T05:00:00+00:00", "remark": APPROVED_DM},
                 {"seq": 2, "role": "State Manager", "decided_role": "Zonal Head",
                  "decision": "approve", "by": "Zubin Head",
                  "decided_at": "2026-11-21T09:45:00+00:00", "remark": ESCALATED},
             ]},
        ],
        **extra,
    }


def _with_internal(**extra: Any) -> dict[str, Any]:
    doc = _doc()
    doc["internal"] = _internal(**extra)
    return doc


def test_the_internal_copy_prints_every_round_step_name_and_remark() -> None:
    page = _text(job.render_html(_with_internal(), internal=True))
    for text in ("Internal copy. Not for the customer.", "Approval trail",
                 "Round 1: Returned for changes", "Round 2: Approved",
                 "order total ₹1,85,000.00", "order total ₹1,66,750.00",
                 "Kiran Officer", "Dilip Manager", RETURNED, APPROVED_DM, ESCALATED,
                 "Re-quoted as asked.", "Deliver before the sowing window.",
                 "Zubin Head (as Zonal Head)", "Not reached", "Returned", "Approved"):
        assert text in page, text
    # 07:10 UTC is 12:40 IST; the trail is on the IST clock
    assert "20 Nov 2026, 12:40" in page and "21 Nov 2026, 15:15" in page
    assert page.index("Round 1") < page.index("Round 2")


def test_the_customer_copy_prints_none_of_it_even_when_the_claim_carries_it() -> None:
    """Rule 1: FS-012 rule 9 still holds for the copy a dealer downloads."""
    doc = _with_internal(amend_reason="Customer cut the quantity", amend_count=1)
    page = _text(job.render_html(doc))
    for text in ("Internal copy", "Approval trail", "Dilip Manager", "Zubin Head",
                 "Kiran Officer", RETURNED, APPROVED_DM, ESCALATED, "Re-quoted",
                 "sowing window", "cut the quantity", "Round 1"):
        assert text not in page, text


def test_an_amended_order_prints_each_rounds_total_and_the_reason() -> None:
    """EC-6: a reader can tell the managers approved a different figure."""
    page = _text(job.render_html(
        _with_internal(amend_reason="Customer cut the quantity", amend_count=1),
        internal=True))
    assert "Amended 1 time. Last reason" in page and "Customer cut the quantity" in page
    assert "order total ₹" in page


def test_an_order_without_a_round_says_so() -> None:
    doc = _doc()
    doc["internal"] = {"remarks": None, "amend_reason": None, "amend_count": 0,
                       "approvals": []}
    page = _text(job.render_html(doc, internal=True))
    assert "No approval round" in page and "Order remarks" not in page


def test_a_claim_without_internal_still_renders_the_internal_copy() -> None:
    """A document from an older claim: the trail is empty, not an error."""
    assert "No approval round" in _text(job.render_html(_doc(), internal=True))


def test_a_remark_is_escaped_not_interpreted() -> None:
    doc = _with_internal()
    doc["internal"]["approvals"][0]["steps"][0]["remark"] = '<img src="http://x/y.png">'
    html = job.render_html(doc, internal=True)
    assert '<img src="http://x' not in html and "&lt;img" in html


def test_the_filename_and_key_of_the_internal_copy() -> None:
    assert pdf_filename("SO/GJ/2026-27/00007", internal=True) == \
        "SO-GJ-2026-27-00007-internal.pdf"
    assert internal_pdf_storage_key("o1", "l1", "n1") == "orders/o1/l1-n1-internal.pdf"
    assert internal_pdf_storage_key("o1", "l1", "n1") != pdf_storage_key("o1", "l1")


class _Store:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data


def _run(monkeypatch: pytest.MonkeyPatch, doc: dict[str, Any],
         done: object = True) -> tuple[str | None, _Store, list[tuple[str, dict]]]:
    calls: list[tuple[str, dict]] = []

    async def call(_settings: object, sql: str, params: dict) -> object:
        calls.append((sql, params))
        return doc if "order_render_claim" in sql else done

    monkeypatch.setattr(job, "_call", call)
    store = _Store()
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    return asyncio.run(job.render_one(settings, store)), store, calls  # type: ignore[arg-type]


def test_mode_both_uploads_both_copies_and_passes_both_keys(
        monkeypatch: pytest.MonkeyPatch) -> None:
    doc = {**_with_internal(), "mode": "both"}
    oid = doc["order"]["id"]
    outcome, store, calls = _run(monkeypatch, doc)
    assert outcome == "ready"
    customer = pdf_storage_key(oid, "lease-a")
    internal = next(k for k in store.objects if k.endswith("-internal.pdf"))
    assert set(store.objects) == {customer, internal}
    # plan review R-2: not derivable from the customer key a dealer's link carries
    assert re.fullmatch(rf"orders/{oid}/lease-a-[0-9a-f]{{32}}-internal\.pdf", internal)
    assert RETURNED.encode() in store.objects[internal]
    assert RETURNED.encode() not in store.objects[customer]
    done = next(p for s, p in calls if "order_render_done" in s)
    assert done["key"] == customer and done["internal"] == internal


def test_mode_internal_renders_only_the_internal_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-1: an order already ready keeps its customer copy; the done passes no key."""
    doc = {**_with_internal(), "mode": "internal"}
    oid = doc["order"]["id"]
    outcome, store, calls = _run(monkeypatch, doc)
    assert outcome == "ready"
    (internal,) = store.objects
    assert internal.startswith(f"orders/{oid}/lease-a-") and internal.endswith("-internal.pdf")
    done = next(p for s, p in calls if "order_render_done" in s)
    assert done["key"] is None and done["internal"] == internal


def _broken(doc: dict, settings: object, *, internal: bool = False) -> tuple[bytes, str]:
    if internal:
        raise RuntimeError("font missing")
    return b"customer", "application/pdf"


def test_a_failed_internal_copy_does_not_hold_back_the_customer_copy(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 8, plan review R-4: the dealer's copy is published; the internal key is
    None, so claim branch 2 owes it."""
    monkeypatch.setattr(job, "render_document", _broken)
    doc = {**_with_internal(), "mode": "both"}
    outcome, store, calls = _run(monkeypatch, doc)
    assert outcome == "ready"
    assert set(store.objects) == {pdf_storage_key(doc["order"]["id"], "lease-a")}
    done = next(p for s, p in calls if "order_render_done" in s)
    assert done["key"] and done["internal"] is None
    assert not any("order_render_failed" in s for s, _ in calls)


def test_a_failed_render_in_mode_internal_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job, "render_document", _broken)
    outcome, store, calls = _run(monkeypatch, {**_with_internal(), "mode": "internal"})
    assert outcome == "failed" and store.objects == {}
    assert any("order_render_failed" in s for s, _ in calls)
    assert not any("order_render_done" in s for s, _ in calls)


def test_a_done_the_database_does_not_have_yet_lets_the_lease_lapse(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan review R-1: the deploy starts this worker before 092 is applied."""
    from sqlalchemy.exc import ProgrammingError

    class MissingError(Exception):
        sqlstate = "42883"

    calls: list[str] = []

    async def call(_settings: object, sql: str, params: dict) -> object:
        calls.append(sql)
        if "order_render_claim" in sql:
            return {**_with_internal(), "mode": "both"}
        raise ProgrammingError(sql, params, MissingError("function does not exist"))

    monkeypatch.setattr(job, "_call", call)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    assert asyncio.run(job.render_one(settings, _Store())) == "failed"  # type: ignore[arg-type]
    assert not any("order_render_failed" in c for c in calls)


def test_any_other_database_error_at_done_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Code review F-1: only a missing function (42883) is the deploy window."""
    from sqlalchemy.exc import ProgrammingError

    class DeniedError(Exception):
        sqlstate = "42501"

    async def call(_settings: object, sql: str, params: dict) -> object:
        if "order_render_claim" in sql:
            return {**_with_internal(), "mode": "both"}
        raise ProgrammingError(sql, params, DeniedError("permission denied"))

    monkeypatch.setattr(job, "_call", call)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    with pytest.raises(ProgrammingError):
        asyncio.run(job.render_one(settings, _Store()))  # type: ignore[arg-type]


@needs_weasyprint
def test_every_page_of_the_internal_copy_says_so_and_a_long_remark_stays_on_it() -> None:
    """EC-10 and EC-11: six rounds of four steps, each remark 2,000 characters with
    no space in it, Gujarati and Devanagari among them."""
    pypdf = pytest.importorskip("pypdf")
    doc = _with_internal()
    run = ("ગુજરાતીલખાણ" + "हिंदीपाठ" + "X" * 100) * 20
    rounds = []
    for n in range(1, 7):
        rounds.append({
            "round": n, "status": "rejected" if n < 6 else "approved", "amount": "166750.00",
            "requested_at": "2026-11-21T03:00:00+00:00", "requested_by": "Kiran Officer",
            "request_remark": run[:1000], "decided_at": "2026-11-21T09:45:00+00:00",
            "steps": [{"seq": s, "role": "District Manager", "decided_role": None,
                       "decision": "approve", "by": "Dilip Manager",
                       "decided_at": "2026-11-21T05:00:00+00:00", "remark": run[:2000]}
                      for s in range(1, 5)]})
    doc["internal"]["approvals"] = rounds
    data = render_pdf(job.render_html(doc, internal=True))
    pages = [p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(data)).pages]
    assert len(pages) > 1
    for i, text in enumerate(pages):
        assert "Internal copy. Not for the customer." in text, f"page {i + 1}"
    assert_every_glyph_on_the_page(data, only=re.compile(r"^X+$"))
