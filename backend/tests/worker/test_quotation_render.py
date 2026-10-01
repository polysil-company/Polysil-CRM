"""The quotation document (FS-005 5.3, 10): the HTML carries every figure the
document holds, as given, and the PDF carries the text a farmer reads.

No database. The HTML tests run everywhere; the PDF tests run where WeasyPrint
imports (CI, the container) and skip with a reason where it does not (the Windows
dev box, which finds a 32-bit GTK).
"""

from __future__ import annotations

import io
import re
import threading
from decimal import Decimal

import pytest

import worker.jobs.quotations as job
from api.config import get_settings
from api.domain.quotations import storage_key
from worker.jobs.quotations import (
    _date,
    _money,
    _plain,
    decode_claim,
    render_html,
    render_pdf,
    renderer_available,
)

GUJARATI_NAME = "રમેશભાઈ પટેલ"
HINDI_TERMS = "भुगतान 7 दिनों में"


def _doc(*, provisional: bool = False, intra: bool = True, party: str = "Rameshbhai Patel",
         terms: str | None = "Prices ex-works.") -> dict:
    return {
        "quotation": {
            "id": "00000000-0000-0000-0000-000000000001", "quote_no": "QT/GJ/2026-27/00001",
            "version": 1, "sales_type": "commercial", "sent_at": "2026-10-01T09:00:00+05:30",
            "valid_until": "2026-11-15", "price_effective_date": "2026-10-01",
            "is_provisional": provisional, "intra_state": intra,
            "seller_legal_name": "Polysil Irrigation Systems Pvt Ltd",
            "seller_address": "Rajkot, Gujarat", "seller_gstin_no": "24AAACP1234A1Z5",
            "seller_state_code": "GJ",
            "party_name": party, "party_address": "Vadod, Anand", "party_mobile": "+919876543210",
            "party_gstin": None, "terms": terms,
            "gross": "1857.42", "discount": "269.32", "taxable": "1588.10",
            "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50",
            "share_token": "t" * 43,
        },
        "lines": [{
            "line_no": 1, "description": "UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985",
            "hsn_code": "3917", "uom": "MTR", "qty": "18.000", "rate": "103.19",
            "gross": "1857.42", "discount_pct": "10.000", "discount1_amt": "185.74",
            "after_discount1": "1671.68", "discount2_pct": "5.000", "discount2_amt": "83.58",
            "after_discount2": "1588.10", "discount3_pct": "0.000", "discount3_amt": "0.00",
            "discount": "269.32", "taxable": "1588.10", "gst_slab": "5.000",
            "cgst_rate": "2.500", "sgst_rate": "2.500", "igst_rate": "0.000",
            "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50",
        }],
    }


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_the_html_carries_every_figure_as_given() -> None:
    doc = _doc()
    html = render_html(doc)
    flat = _text(html)
    line = doc["lines"][0]
    # Indian grouping, no trailing zeros on rates (demo walk D-5)
    for key in ("gross", "discount1_amt", "after_discount1", "discount2_amt", "after_discount2",
                "taxable", "cgst", "sgst", "total", "rate"):
        assert _money(line[key]) in flat, key
    for key in ("discount_pct", "discount2_pct", "cgst_rate", "sgst_rate"):
        assert _plain(line[key]) + "%" in flat, key
    assert "1,857.42" in flat and "\u20b91,667.50" in flat and "Amounts in Indian rupees" in flat
    assert "3rd disc" not in flat, "a tier no line uses prints no columns"
    assert " 18 " in flat and "10.000" not in flat, "quantities and rates without trailing zeros"
    q = doc["quotation"]
    for key in ("gross", "discount", "taxable", "cgst", "sgst", "total"):
        assert _money(q[key]) in flat, key
    assert q["quote_no"] in flat and q["seller_gstin_no"] in flat and q["party_name"] in flat
    assert "IGST" not in flat, "an intra-state document prints CGST and SGST"
    assert "INDICATIVE PRICING" not in flat.upper()


def test_the_banner_appears_exactly_when_the_pricing_is_provisional() -> None:
    assert "Indicative pricing" in render_html(_doc(provisional=True))
    assert "Indicative pricing" not in render_html(_doc(provisional=False))


def test_an_inter_state_document_prints_igst_instead() -> None:
    flat = _text(render_html(_doc(intra=False)))
    assert "IGST" in flat and "CGST" not in flat


def test_the_template_does_no_arithmetic_and_escapes_what_it_prints() -> None:
    """Money arrives formatted; a value with markup in it is text, not markup."""
    html = render_html(_doc(party="<b>Not</b> Bold", terms=None))
    assert "&lt;b&gt;Not&lt;/b&gt; Bold" in html and "<b>Not</b>" not in html
    assert "Terms" not in _text(html)


def test_the_font_stack_names_the_indic_faces() -> None:
    html = render_html(_doc())
    assert "Noto Sans Gujarati" in html and "Noto Sans Devanagari" in html


def test_the_send_date_prints_on_the_ist_calendar() -> None:
    """Code review F-10: sent_at is stored in UTC, and 19:00 UTC on the 5th is the
    6th in India. The document's dates all sit on the IST calendar."""
    assert _date("2026-10-05T19:00:00+00:00") == "06 Oct 2026"
    assert _date("2026-10-05T19:00:00.123456+00:00") == "06 Oct 2026"
    assert _date("2026-10-05T18:29:59+00:00") == "05 Oct 2026"
    assert _date("2026-11-15") == "15 Nov 2026"
    assert _date(None) == ""


def test_the_claim_decodes_money_as_decimal() -> None:
    """Code review F-9, rule 4: never a float on the money path, whichever shape
    the driver hands the jsonb in."""
    doc = decode_claim('{"quotation": {"total": 53387.74}, "lines": [{"rate": 103.19}]}')
    assert doc["quotation"]["total"] == Decimal("53387.74")
    assert isinstance(doc["lines"][0]["rate"], Decimal)
    again = decode_claim({"quotation": {"total": 0.1}, "lines": []})
    assert isinstance(again["quotation"]["total"], Decimal)


# ── the PDF, where the renderer imports ──────────────────────────────────────

_problem = renderer_available()
needs_weasyprint = pytest.mark.skipif(
    _problem is not None, reason=f"WeasyPrint does not import here: {_problem}")


def _pdf_text(data: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@needs_weasyprint
def test_the_pdf_is_a_pdf_and_carries_the_figures() -> None:
    data = render_pdf(render_html(_doc()))
    assert data[:5] == b"%PDF-"
    text = _pdf_text(data)
    for figure in ("1857.42", "185.74", "1588.10", "1667.50", "QT/GJ/2026-27/00001"):
        assert figure in text, figure


@needs_weasyprint
def test_a_gujarati_name_and_hindi_terms_survive_the_text_layer() -> None:
    """Edge case 12: DejaVu alone renders a Gujarati name as boxes. The image
    carries Noto for both scripts; here the assertion is on the text layer,
    which is what a search or a screen reader gets."""
    data = render_pdf(render_html(_doc(party=GUJARATI_NAME, terms=HINDI_TERMS)))
    text = _pdf_text(data)
    assert GUJARATI_NAME in text and HINDI_TERMS in text



@needs_weasyprint
def test_every_glyph_of_the_widest_table_lies_on_the_page() -> None:
    """Cross-vendor A-3: text extraction passes even for text off the page, so
    the positions are checked against the media box. Intra-state is the wider
    table (CGST and SGST), and the longest figures are used."""
    pypdf = pytest.importorskip("pypdf")
    doc = _doc()
    for key in ("gross", "taxable", "total"):
        doc["lines"][0][key] = "99999999.99"
    reader = pypdf.PdfReader(io.BytesIO(render_pdf(render_html(doc))))
    for page in reader.pages:
        width = float(page.mediabox.width)
        ends: list[tuple[float, str]] = []

        def visit(text: str, cm: list, tm: list, _font: object, size: float,
                  ends: list[tuple[float, str]] = ends) -> None:
            if not text.strip():
                return
            scale = cm[0] * tm[0] or 1.0
            start = cm[4] + tm[4] * cm[0]
            # PR #10 review: the start alone passes a figure that overruns the edge
            # by less than its own width. Half an em per character is a floor for
            # Noto Sans digits, so the estimate never flatters the layout.
            ends.append((start + 0.5 * size * scale * len(text.strip()), text.strip()))

        page.extract_text(visitor_text=visit)
        assert ends, "no text on the page"
        widest = max(ends)
        assert widest[0] <= width, (widest, width)


def test_a_stale_worker_writes_beside_the_published_document(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Cross-vendor A-4 and A-5: a worker whose lease was reclaimed uploads under
    its own key, so the published object is untouched, and the render and upload
    run off the event loop."""
    import asyncio

    doc = _doc()
    qid, version = doc["quotation"]["id"], doc["quotation"]["version"]
    published = storage_key(qid, version, "lease-a")
    store: dict[str, bytes] = {published: b"the document the farmer has"}
    loop_thread: list[int] = []
    put_threads: list[int] = []

    class Store:
        def put(self, key: str, data: bytes, content_type: str) -> None:
            put_threads.append(threading.get_ident())
            store[key] = data

    async def claim(_settings: object) -> dict:
        loop_thread.append(threading.get_ident())
        return {**doc, "lease_token": "lease-b", "attempt": 2}

    async def done(*_: object) -> bool:
        return False            # someone else reclaimed and finished it

    monkeypatch.setattr(job, "_claim", claim)
    monkeypatch.setattr(job, "_done", done)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    assert asyncio.run(job.render_one(settings, Store())) == "stale"  # type: ignore[arg-type]
    assert store[published] == b"the document the farmer has"
    assert storage_key(qid, version, "lease-b") in store
    assert put_threads and put_threads[0] != loop_thread[0], "the upload ran on the loop"



def test_a_render_tick_stops_at_its_budget_and_never_overlaps(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """PR #10 review: without a budget a backlog of slow renders held a tick for
    minutes, and overlapping ticks filled the job slots the outbox drain needs."""
    import asyncio

    calls: list[int] = []

    async def slow_render(*_: object) -> str:
        calls.append(1)
        await asyncio.sleep(0.05)
        return "ready"

    settings = get_settings().model_copy(update={"pdf_render_budget": 0.12})
    monkeypatch.setattr(job, "render_one", slow_render)
    monkeypatch.setattr(job, "get_settings", lambda: settings)

    async def two_ticks() -> tuple[int, int]:
        first = asyncio.create_task(job.quotation_render_due({"storage": object()}))
        await asyncio.sleep(0.01)
        second = await job.quotation_render_due({"storage": object()})
        return await first, second

    handled, overlapped = asyncio.run(two_ticks())
    assert overlapped == 0, "a tick that finds one running does nothing"
    assert 1 <= handled <= 4, handled
    assert asyncio.run(job.quotation_render_due({"storage": object()})) >= 1, "the guard resets"
