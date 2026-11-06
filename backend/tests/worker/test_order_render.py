"""The order PDF (FS-012 rules 6 and 9): the HTML carries every figure as given,
the payment terms and the place of supply, and never a remark; a stale worker
writes beside the published document. No database: the lease is in
tests/db/test_migration_016.py."""

from __future__ import annotations

import asyncio
import threading

import pytest

import worker.jobs.orders as job
from api.config import get_settings
from api.domain.orders import pdf_filename, pdf_storage_key
from tests.worker.test_quotation_render import _doc as _quotation_doc
from tests.worker.test_quotation_render import _text, needs_weasyprint
from worker.jobs.quotations import render_pdf


def _doc(*, intra: bool = True) -> dict:
    q = _quotation_doc(intra=intra)
    quotation_only = ("quote_no", "version", "sent_at", "valid_until", "terms", "share_token")
    o = {k: v for k, v in q["quotation"].items() if k not in quotation_only}
    o.update(order_no="SO/GJ/2026-27/00007", order_type="commercial", status="approved",
             submitted_at="2026-10-02T10:00:00+05:30", approved_at="2026-10-03T00:30:00+05:30",
             payment_terms="full_payment", place_of_supply="Gujarat",
             delivery_address="Farm 12, Vadod")
    return {"order": o, "lines": q["lines"], "lease_token": "lease-a", "attempt": 1}


def test_the_html_carries_every_figure_and_the_order_facts() -> None:
    page = _text(job.render_html(_doc()))
    for figure in ("SO/GJ/2026-27/00007", "1,857.42", "185.74", "1,588.10", "39.70",
                   "₹1,667.50",
                   "24AAACP1234A1Z5", "Rameshbhai Patel", "Farm 12, Vadod", "Gujarat",
                   "Full payment"):
        assert figure in page, figure
    # 00:30 IST on the 3rd is the 2nd in UTC; the approval date is the IST one
    assert "Approved 03 Oct 2026" in page


def test_an_inter_state_order_prints_igst() -> None:
    page = job.render_html(_doc(intra=False))
    assert "IGST" in page and "CGST" not in page


def test_no_remark_reaches_the_document_even_if_the_claim_carried_one() -> None:
    """Rule 9: the claim strips remarks, and the template does not print them."""
    doc = _doc()
    doc["order"].update(remarks="internal: rate too low", cancel_remark="x", close_remark="y")
    assert "internal" not in job.render_html(doc)


def test_the_filename_is_safe() -> None:
    assert pdf_filename("SO/GJ/2026-27/00007") == "SO-GJ-2026-27-00007.pdf"


def test_a_stale_worker_writes_beside_the_published_document(
        monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _doc()
    oid = doc["order"]["id"]
    published = pdf_storage_key(oid, "lease-a")
    store: dict[str, bytes] = {published: b"the approved order"}
    loop_thread: list[int] = []
    put_threads: list[int] = []

    class Store:
        def put(self, key: str, data: bytes, content_type: str) -> None:
            put_threads.append(threading.get_ident())
            store[key] = data

    async def call(_settings: object, sql: str, _params: object) -> object:
        loop_thread.append(threading.get_ident())
        if "order_render_claim" in sql:
            return {**doc, "lease_token": "lease-b", "attempt": 2}
        return False            # someone else reclaimed and finished it

    monkeypatch.setattr(job, "_call", call)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    assert asyncio.run(job.render_one(settings, Store())) == "stale"  # type: ignore[arg-type]
    assert store[published] == b"the approved order"
    assert pdf_storage_key(oid, "lease-b") in store
    assert put_threads and put_threads[0] != loop_thread[0], "the upload ran on the loop"


def test_a_render_error_is_recorded_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def call(_settings: object, sql: str, params: dict) -> object:
        calls.append(sql)
        return _doc() if "claim" in sql else True

    class Broken:
        def put(self, *_: object) -> None:
            raise RuntimeError("bucket missing")

    monkeypatch.setattr(job, "_call", call)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    assert asyncio.run(job.render_one(settings, Broken())) == "failed"  # type: ignore[arg-type]
    assert any("order_render_failed" in c for c in calls)


@needs_weasyprint
def test_the_pdf_is_a_pdf_and_carries_the_order_number() -> None:
    pypdf = pytest.importorskip("pypdf")
    import io
    data = render_pdf(job.render_html(_doc()))
    assert data[:5] == b"%PDF-"
    text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(data)).pages)
    for figure in ("SO/GJ/2026-27/00007", "1,667.50"):
        assert figure in text, figure


def test_an_order_pdf_carries_no_company_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """FS-064 rule 22, from the order's side: the profile follows quotations only.
    Through the order's own `render_document`, with the renderer replaced so it
    runs where WeasyPrint does not import."""
    import io

    import pypdf

    from tests.worker.test_quotation_render import _one_page

    monkeypatch.setattr(job, "renderer_available", lambda: None)
    monkeypatch.setattr(job, "render_pdf", lambda _html: _one_page("Order"))
    settings = get_settings().model_copy(update={"pdf_renderer": "weasyprint",
                                                 "quotation_profile_enabled": True})
    data, content_type = job.render_document(_doc(), settings)
    assert content_type == "application/pdf"
    assert len(pypdf.PdfReader(io.BytesIO(data)).pages) == 1


def test_freight_is_a_row_of_its_own_so_the_rows_add_up() -> None:
    """FS-069 rule 16: the order's tax and total include freight, so a Freight row
    with its own taxable, tax and total makes the rows reconcile."""
    doc = _doc()
    o = doc["order"]
    o.update(freight_amount="500.00", freight_slab="18", freight_slab_chosen=False,
             freight_cgst="45.00", freight_sgst="45.00", freight_igst="0.00",
             freight_total="590.00")
    page = _text(job.render_html(doc))
    assert "Freight" in page
    assert "₹500.00 45.00 (9%) 45.00 (9%) ₹590.00" in page


def test_no_freight_row_without_freight() -> None:
    assert "Freight" not in _text(job.render_html(_doc()))
