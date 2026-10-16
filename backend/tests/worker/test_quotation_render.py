"""The quotation document (FS-005 5.3, 10; FS-064): the HTML is the client's own
sheet and carries every figure the document holds, the PDF carries the text a
farmer reads, and the company profile follows it in the same file.

No database. The HTML and merge tests run everywhere; the PDF tests run where
WeasyPrint imports (CI, the container) and skip with a reason where it does not
(the Windows dev box, which finds a 32-bit GTK).
"""

from __future__ import annotations

import asyncio
import io
import re
import threading
from decimal import Decimal
from typing import Any

import pypdf
import pytest

import worker.jobs.quotations as job
from api.config import get_settings
from api.domain.quotations import storage_key
from worker.jobs.quotations import (
    _date,
    _money,
    append_profile,
    company_profile,
    decode_claim,
    profile_problem,
    render_document,
    render_html,
    render_pdf,
    renderer_available,
)
from worker.sample_quotation import PAGE_ONE_FIGURES
from worker.sample_quotation import document as _doc

GUJARATI_NAME = "રમેશભાઈ પટેલ"
HINDI_TERMS = "भुगतान 7 दिनों में"
APPROVER = "Asha Mehta"

# the sample's two lines as one row each on the page (worker/sample_quotation.py)
ROW_1 = "1 UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985 ₹103.19 ₹88.23 18 MTR ₹269.32 ₹1,588.10"
ROW_2 = "2 END PLUG WITH QUICK ACTION COUPLER 90MM ₹50.00 ₹45.00 4 NOS ₹20.00 ₹180.00"


def _text(html: str) -> str:
    """What a reader sees: the body's text, without the stylesheet."""
    body = html[html.index("<body"):]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).replace("&#39;", "'")


def _flat(doc: dict) -> str:
    return _text(render_html(doc))


# ── the client's sheet (FS-064) ──────────────────────────────────────────────

def test_every_label_of_the_clients_sheet_prints() -> None:
    flat = _flat(_doc())
    for label in ("POLYSIL IRRIGATION SYSTEMS LTD", "Dist-Vadodara 391780", "Quotation",
                  "Dealer Name and Contact detail", "Farmer/Client Name", "MIS System",
                  "Village", "Contact Number", "Taluka", "District", "State",
                  "Effective Rate Date", "Sr. No.", "Material Description", "Price",
                  "Price after Dis.", "Qty.", "Discount. Amt.", "Total Amt.", "Sub Total",
                  "Total Discount Amt.", "Remark", "This quotation is valid for 45 days",
                  "has the right to change rates", "a signature is not required",
                  "Quotation made by: Ravi Kumar", "www.polysilirrigation.com"):
        assert label in flat, label
    # what we add where the sheet has blank cells (GAP-486)
    for label in ("Quotation No.", "Date", "Valid Until", "GSTIN"):
        assert label in flat, label
    assert "(B)" not in flat, "the leftover section mark of the UP sheet"


def test_the_header_carries_the_print_block_and_the_quotations_own_fields() -> None:
    doc = _doc()
    flat = _flat(doc)
    # label and value together, each value distinct: a blank or swapped cell
    # passed while "Vadod" was also in the address and both dates were 1 Oct (F-2)
    for cell in ("Dealer Name and Contact detail Shree Agro, Bhavesh Shah, 9876500000 Farmer",
                 "Farmer/Client Name Rameshbhai Patel Near the dairy, Anand road MIS System "
                 "Sprinkler",
                 "Village Vadod Contact Number +91 98765 43210",
                 "Taluka Gondal Quotation No. QT/GJ/2026-27/00001",
                 "District Rajkot Date 01 Oct 2026",
                 "State Gujarat Valid Until 15 Nov 2026",
                 "Effective Rate Date 03 Oct 2026 GSTIN 24AAACP1234A1Z5"):
        assert cell in flat, cell
    assert "+91 98765 43210" in flat and "+919876543210" not in flat
    assert "(version" not in flat, "version 1 prints no version mark"
    doc["quotation"]["version"] = 2
    assert "QT/GJ/2026-27/00001 (version 2)" in _flat(doc)


def test_the_line_prints_seven_columns_and_folds_the_tiers() -> None:
    flat = _flat(_doc())
    # each row whole and in order: Price, Price after Dis., Qty. with its unit,
    # Discount. Amt., Total Amt. Neither row's figures appear in the totals
    assert ROW_1 in flat and ROW_2 in flat
    assert f"{ROW_1} {ROW_2} Sub Total" in flat
    for gone in ("HSN", " 3917 ", "Disc %", "2nd disc", "185.74", "83.58", "1,671.68",
                 "Line total", "Taxable"):
        assert gone not in flat, f"{gone} is not on the client's sheet"
    assert "10.000" not in flat and "18.000" not in flat, "no trailing zeros"
    assert "Price after Dis. is rounded to the paisa" in flat
    assert "Total Amt. is Price x Qty. less Discount. Amt." in flat


def test_the_totals_print_as_given() -> None:
    doc = _doc()
    flat = _flat(doc)
    q = doc["quotation"]
    assert (f"Sub Total ₹{_money(q['taxable'])} CGST @ 2.5% ₹{_money(q['cgst'])} "
            f"SGST @ 2.5% ₹{_money(q['sgst'])} Total ₹{_money(q['total'])} "
            f"Total Discount Amt. ₹{_money(q['discount'])} Amounts in Indian rupees") in flat
    assert "Sub Total ₹1,768.10 CGST @ 2.5% ₹44.20" in flat and "Total ₹1,856.50" in flat
    assert "IGST" not in flat, "an intra-state document prints CGST and SGST"
    assert "Amounts in Indian rupees" in flat and "INDICATIVE PRICING" not in flat.upper()
    assert "each component is rounded on its own" in flat, "the per-line rounding sentence stays"


def test_a_tax_row_names_its_rate_only_when_every_line_shares_it() -> None:
    doc = _doc(lines=2)
    doc["lines"][1].update(gst_slab="18.000", cgst_rate="9.000", sgst_rate="9.000")
    flat = _flat(doc)
    assert "CGST ₹" in flat and "SGST ₹" in flat and "@" not in flat


def test_an_inter_state_document_prints_one_igst_row_and_the_place_of_supply() -> None:
    doc = _doc(intra=False)
    doc["quotation"].update(cgst="0.00", sgst="0.00", igst="88.40")
    for line in doc["lines"]:
        line.update(cgst_rate="0.000", sgst_rate="0.000", igst_rate="5.000")
    doc["print"]["supply_state"] = "Rajasthan"
    flat = _flat(doc)
    assert "Sub Total ₹1,768.10 IGST @ 5% ₹88.40 Total ₹1,856.50 Total Discount" in flat
    assert "CGST" not in flat and "SGST" not in flat
    assert "Place of Supply Rajasthan" in flat
    assert "Place of Supply" not in _flat(_doc()), "not printed when it is the lead's own state"


def test_an_export_prints_its_country_and_its_tax_treatment() -> None:
    lut = _doc(intra=False)
    lut["quotation"].update(tax_treatment="export_lut", export_country="Kenya",
                            lut_arn="AD240326000001X", cgst="0.00", sgst="0.00", igst="0.00",
                            total="1768.10")
    flat = _flat(lut)
    assert "Place of Supply Outside India (Kenya)" in flat
    assert "IGST" not in flat.replace("without payment of IGST", "") and "CGST" not in flat
    assert "export under LUT without payment of IGST (ARN AD240326000001X)" in flat
    # the grand total row itself: "Total ₹..." alone is also inside "Sub Total ₹..."
    assert "Sub Total ₹1,768.10 Total ₹1,768.10 Total Discount Amt. ₹289.32" in flat

    paid = _doc(intra=False)
    paid["quotation"].update(tax_treatment="export_igst", export_country="Kenya",
                             cgst="0.00", sgst="0.00", igst="88.40")
    for line in paid["lines"]:
        line.update(cgst_rate="0.000", sgst_rate="0.000", igst_rate="5.000")
    flat = _flat(paid)
    assert "IGST @ 5% ₹88.40 Total ₹1,856.50" in flat and "export under LUT" not in flat
    assert "Outside India (Kenya)" in flat


def test_the_buyers_gstin_prints_when_there_is_one() -> None:
    doc = _doc()
    assert "GSTIN 27" not in _flat(doc)
    doc["quotation"]["party_gstin"] = "27AAACB1234C1Z9"
    assert "GSTIN 27AAACB1234C1Z9" in _flat(doc)


def test_no_dealer_leaves_the_row_empty() -> None:
    doc = _doc()
    doc["print"].update(dealer_name=None, dealer_contact=None, dealer_mobile=None)
    flat = _flat(doc)
    assert "Dealer Name and Contact detail Farmer/Client Name" in flat


def test_no_approver_is_named_anywhere() -> None:
    """FS-012 rules 2 and 9, GAP-493: a partner never learns who approved, and
    this is the document a dealer and a farmer open."""
    doc = _doc()
    doc["print"]["approved_by"] = APPROVER      # even if a later claim carried one
    html = render_html(doc)
    assert APPROVER not in html and "approved by" not in html.lower()


def test_the_banner_sits_under_the_title_exactly_when_the_pricing_is_provisional() -> None:
    html = render_html(_doc(provisional=True))
    assert "Indicative pricing" in html
    assert html.index("Indicative pricing") < html.index("Sr. No."), "page one, above the lines"
    assert "Indicative pricing" not in render_html(_doc(provisional=False))


def test_the_template_escapes_what_it_prints_and_an_empty_remark_keeps_its_label() -> None:
    html = render_html(_doc(party="<b>Not</b> Bold", terms=None))
    assert "&lt;b&gt;Not&lt;/b&gt; Bold" in html and "<b>Not</b>" not in html
    assert "Remark This quotation is valid" in _text(html)
    assert "Remark Prices ex-works." in _flat(_doc())


def test_the_font_stack_names_the_indic_faces() -> None:
    html = render_html(_doc())
    assert "Noto Sans Gujarati" in html and "Noto Sans Devanagari" in html


def test_the_logo_is_embedded_and_needs_no_file_access() -> None:
    """Client item 5: the logo prints on the page; a data URI, so the renderer
    reads nothing from disk."""
    assert '<img class="logo" src="data:image/png;base64,' in render_html(_doc())


def test_a_subsidised_quotation_prints_its_block_with_the_cost_as_calculated() -> None:
    """FS-057 rule 7 under the state sheets' heading (FS-064 rule 19). Never the
    sheets' `Unit Cost` label: that is the government's table value, and the
    figure here is the calculated cost (GAP-497)."""
    doc = _doc()
    assert "Subsidy and Farmer Share" not in render_html(doc)
    doc["subsidy"] = {"scheme_code": "CG", "category_name": "Small farmer (55%)",
                      "total_cost": "66495.44", "flat_charge": 1003, "subsidy": "36204.85",
                      "farmer_share": "31293.59"}
    flat = _flat(doc)
    assert "Subsidy and Farmer Share (CG)" in flat
    assert "Farmer Category Small farmer (55%)" in flat
    assert "Cost as calculated ₹66,495.44" in flat and "plus inspection ₹1,003.00" in flat
    assert "Subsidy ₹36,204.85" in flat and "Farmer Share ₹31,293.59" in flat
    assert "Unit Cost" not in flat
    doc["subsidy"]["flat_charge"] = 0
    assert "plus inspection" not in _flat(doc)
    # the category wraps, the amounts do not (F-4)
    html = render_html(doc)
    assert "<td>Small farmer (55%)</td>" in html and '<td class="n">₹66,495.44</td>' in html


# ── the print block (FS-064 rules 27 and 28) ─────────────────────────────────

@pytest.mark.parametrize(("change", "message"), [
    (lambda d: d.pop("print"), "migration 076 is not applied"),
    (lambda d: d.update(print=None), "print block is empty"),
    (lambda d: d.update(print={"error": "two talukas above one village"}),
     "two talukas above one village"),
])
def test_a_claim_without_a_usable_print_block_fails_and_stores_nothing(
        monkeypatch: pytest.MonkeyPatch, change: Any, message: str) -> None:
    """Edge cases 1 and 2. A new worker claims from the old function for as long
    as the migration runs: a blank header published then could not be recalled."""
    doc = _doc()
    change(doc)
    with pytest.raises(RuntimeError, match=message):
        render_html(doc)

    store: dict[str, bytes] = {}
    failed: list[str] = []

    class Store:
        def put(self, key: str, data: bytes, content_type: str) -> None:
            store[key] = data

    async def claim(_settings: object) -> dict:
        return {**doc, "lease_token": "lease-a", "attempt": 1}

    async def record(_s: object, _q: str, _lease: str, error: str) -> bool:
        failed.append(error)
        return True

    monkeypatch.setattr(job, "_claim", claim)
    monkeypatch.setattr(job, "_failed", record)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    assert asyncio.run(job.render_one(settings, Store())) == "failed"  # type: ignore[arg-type]
    assert store == {} and len(failed) == 1 and message in failed[0]


# ── dates and decoding ───────────────────────────────────────────────────────

def test_the_send_date_prints_on_the_ist_calendar() -> None:
    """Code review F-10: sent_at is stored in UTC, and 19:00 UTC on the 5th is the
    6th in India. The document's dates all sit on the IST calendar."""
    assert _date("2026-10-05T19:00:00+00:00") == "06 Oct 2026"
    assert _date("2026-10-05T19:00:00.123456+00:00") == "06 Oct 2026"
    assert _date("2026-10-05T18:29:59+00:00") == "05 Oct 2026"
    assert _date("2026-11-15") == "15 Nov 2026"
    assert _date(None) == ""


def test_the_validity_days_count_from_the_ist_send_date() -> None:
    """A send at 00:30 IST on the 6th is 19:00 UTC on the 5th: 40 days to the
    15th of November, not 41."""
    doc = _doc()
    doc["quotation"]["sent_at"] = "2026-10-05T19:00:00+00:00"
    assert "valid for 40 days" in _flat(doc)
    doc["quotation"]["valid_until"] = "2026-10-07"
    assert "valid for 1 day from" in _flat(doc)


def test_the_claim_decodes_money_as_decimal() -> None:
    """Code review F-9, rule 4: never a float on the money path, whichever shape
    the driver hands the jsonb in."""
    doc = decode_claim('{"quotation": {"total": 53387.74}, "lines": [{"rate": 103.19}]}')
    assert doc["quotation"]["total"] == Decimal("53387.74")
    assert isinstance(doc["lines"][0]["rate"], Decimal)
    again = decode_claim({"quotation": {"total": 0.1}, "lines": []})
    assert isinstance(again["quotation"]["total"], Decimal)


@pytest.mark.parametrize(("raw", "shown"), [
    ("+919876543210", "+91 98765 43210"), ("919876543210", "+91 98765 43210"),
    ("+14155550100", "+14155550100"), ("", ""), (None, "")])
def test_the_mobile_filter(raw: str | None, shown: str) -> None:
    from worker.jobs.quotations import _mobile
    assert _mobile(raw) == shown


# ── the company profile, without the renderer (FS-064 rules 21 to 26) ────────

def _one_page(title: str = "Quotation QT/GJ/2026-27/00001 v1") -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_metadata({"/Title": title})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _sizes(data: bytes) -> list[tuple[int, int]]:
    reader = pypdf.PdfReader(io.BytesIO(data))
    return [(round(float(p.mediabox.width)), round(float(p.mediabox.height)))
            for p in reader.pages]


def test_the_committed_profile_is_the_clients_seven_landscape_pages() -> None:
    reader = pypdf.PdfReader(io.BytesIO(company_profile()))
    assert not reader.is_encrypted and len(reader.pages) == 7
    assert set(_sizes(company_profile())) == {(842, 595)}
    assert profile_problem() is None


def test_the_profile_follows_the_quotation_and_the_title_survives() -> None:
    merged = append_profile(_one_page(), company_profile())
    assert _sizes(merged) == [(595, 842)] + [(842, 595)] * 7
    title = pypdf.PdfReader(io.BytesIO(merged)).metadata.title
    assert title == "Quotation QT/GJ/2026-27/00001 v1"


@pytest.mark.parametrize("bad", [b"", b"%PDF-1.7\n1 0 obj\n<<", b"not a pdf at all"])
def test_an_unreadable_profile_raises(bad: bytes) -> None:
    with pytest.raises(Exception):  # noqa: B017  pypdf raises several types
        append_profile(_one_page(), bad)


def test_an_encrypted_profile_raises() -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=842, height=595)
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="encrypted"):
        append_profile(_one_page(), out.getvalue())


def _patched(monkeypatch: pytest.MonkeyPatch) -> None:
    """The renderer replaced by a one-page PDF, so `render_document` runs on a box
    where WeasyPrint does not import."""
    monkeypatch.setattr(job, "renderer_available", lambda: None)
    monkeypatch.setattr(job, "render_pdf", lambda _html: _one_page())


def test_every_quotation_pdf_ends_with_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 21, through the function the job calls: deleting the append from
    `render_document` fails here."""
    _patched(monkeypatch)
    on = get_settings().model_copy(update={"pdf_renderer": "weasyprint",
                                           "quotation_profile_enabled": True})
    data, content_type = render_document(_doc(), on)
    assert content_type == "application/pdf"
    assert _sizes(data) == [(595, 842)] + [(842, 595)] * 7

    off = on.model_copy(update={"quotation_profile_enabled": False})
    assert _sizes(render_document(_doc(), off)[0]) == [(595, 842)]


def test_the_html_mode_carries_no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    _patched(monkeypatch)
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    data, content_type = render_document(_doc(), settings)
    assert content_type.startswith("text/html") and data == render_html(_doc()).encode("utf-8")


def test_a_missing_profile_fails_the_render_and_not_the_import(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Edge case 8, rule 26: the file is read on first use, so the module (and
    the worker with it) imports without it; the render names the reason."""
    _patched(monkeypatch)
    monkeypatch.setattr(job, "PROFILE", tmp_path / "gone.pdf")
    job.company_profile.cache_clear()
    try:
        assert "FileNotFoundError" in (profile_problem() or "")
        settings = get_settings().model_copy(update={"pdf_renderer": "weasyprint"})
        with pytest.raises(RuntimeError, match="company profile could not be appended"):
            render_document(_doc(), settings)
        off = settings.model_copy(update={"quotation_profile_enabled": False})
        assert _sizes(render_document(_doc(), off)[0]) == [(595, 842)], "the switch is the way out"
    finally:
        job.company_profile.cache_clear()


# ── the PDF, where the renderer imports ──────────────────────────────────────

_problem = renderer_available()
needs_weasyprint = pytest.mark.skipif(
    _problem is not None, reason=f"WeasyPrint does not import here: {_problem}")


def _pages(data: bytes) -> list[str]:
    reader = pypdf.PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


@needs_weasyprint
def test_the_pdf_is_a_portrait_pdf_and_carries_the_figures() -> None:
    data = render_pdf(render_html(_doc()))
    assert data[:5] == b"%PDF-"
    assert _sizes(data) == [(595, 842)]
    text = "\n".join(_pages(data))
    for figure in PAGE_ONE_FIGURES:
        assert figure in text, figure
    assert "QT/GJ/2026-27/00001, page 1 of 1" in " ".join(text.split())
    assert pypdf.PdfReader(io.BytesIO(data)).metadata.title == "Quotation QT/GJ/2026-27/00001 v1"


@needs_weasyprint
def test_the_rendered_quotation_ends_with_the_profile() -> None:
    settings = get_settings().model_copy(update={"pdf_renderer": "weasyprint"})
    data, _ = render_document(_doc(), settings)
    assert _sizes(data) == [(595, 842)] + [(842, 595)] * 7
    assert "QT/GJ/2026-27/00001" in _pages(data)[0], "the text layer survives the merge"
    assert pypdf.PdfReader(io.BytesIO(data)).metadata.title == "Quotation QT/GJ/2026-27/00001 v1"


@needs_weasyprint
def test_a_gujarati_name_and_hindi_terms_survive_the_text_layer() -> None:
    """Edge case 12: DejaVu alone renders a Gujarati name as boxes. The image
    carries Noto for both scripts; here the assertion is on the text layer,
    which is what a search or a screen reader gets."""
    text = "\n".join(_pages(render_pdf(render_html(_doc(party=GUJARATI_NAME, terms=HINDI_TERMS)))))
    assert GUJARATI_NAME in text and HINDI_TERMS in text


@needs_weasyprint
def test_every_glyph_of_the_widest_page_lies_on_the_page() -> None:
    """Cross-vendor A-3: text extraction passes even for text off the page, so
    the positions are checked against the media box. The widest figure is the
    document total over 200 lines at the line ceiling, and a description with no
    space in it cannot push the amounts out (FS-064 edge case 10)."""
    doc = _doc(lines=3)
    for line in doc["lines"]:
        line.update(rate="99999999.99", gross="99999999.99", taxable="99999999.99",
                    discount="99999999.99", qty="1000000",
                    description="HDPE-COIL-63MM-PE100-" + "X" * 179)
    doc["quotation"].update(taxable="19999999998.00", total="19999999998.00",
                            discount="19999999998.00", cgst="499999999.95", sgst="499999999.95")
    doc["quotation"]["party_name"] = "N" * 200
    # outside any table: the remark and the maker's name (F-5); and the longest
    # category the masters hold, three times over (F-4)
    doc["quotation"]["terms"] = "T" * 200
    doc["print"].update(village="V" * 120, dealer_name="D" * 200, made_by="M" * 200)
    doc["subsidy"] = {"scheme_code": "GJ", "category_name": "SC+ST(TRIBAL)+DarkZone90%" * 4,
                      "total_cost": "19999999998.00", "flat_charge": 1003,
                      "subsidy": "19999999998.00", "farmer_share": "19999999998.00"}
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


@needs_weasyprint
def test_sixty_lines_print_their_totals_once_and_number_their_pages() -> None:
    """Edge case 9: totals in a tfoot would repeat under every page's lines."""
    pages = _pages(render_pdf(render_html(_doc(lines=60))))
    assert len(pages) >= 2
    text = "\n".join(pages)
    assert text.count("Sub Total") == 1 and text.count("Total Discount Amt.") == 1
    assert text.count("Material Description") == len(pages) or \
        text.count("Material Description") == len(pages) - 1, "the column header repeats"
    last_with_totals = next(i for i, p in enumerate(pages) if "Sub Total" in p)
    assert "MTR" in pages[last_with_totals], "the totals never sit alone on a page"
    for n in range(1, len(pages) + 1):
        assert f"page {n} of {len(pages)}" in pages[n - 1]


@needs_weasyprint
@pytest.mark.parametrize("count", range(40, 51))
def test_the_totals_stay_whole_and_keep_a_line_with_them(count: int) -> None:
    """Rule 29 at the counts where it bites: 60 lines pass with both break rules
    deleted, while 45 and 46 split the totals and 47 leaves them alone on a page
    (code review F-3). Every page's margin names the quotation."""
    pages = [" ".join(p.split()) for p in _pages(render_pdf(render_html(_doc(lines=count))))]
    [holder] = [p for p in pages if "Sub Total" in p]
    assert "Total Discount Amt." in holder, "the totals split across pages"
    assert "MTR" in holder or "NOS" in holder, "the totals sit alone on a page"
    for n, page in enumerate(pages, 1):
        assert f"QT/GJ/2026-27/00001, page {n} of {len(pages)}" in page


@needs_weasyprint
def test_a_long_remark_breaks_across_pages() -> None:
    terms = " ".join(f"Clause {n}: payment and delivery terms apply." for n in range(45))[:2000]
    pages = _pages(render_pdf(render_html(_doc(lines=40, terms=terms))))
    text = " ".join(" ".join(pages).split())
    assert "Clause 0:" in text and terms.split()[-1] in text
    assert "www.polysilirrigation.com" in pages[-1]


# ── the job ──────────────────────────────────────────────────────────────────

def test_a_stale_worker_writes_beside_the_published_document(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Cross-vendor A-4 and A-5: a worker whose lease was reclaimed uploads under
    its own key, so the published object is untouched, and the render and upload
    run off the event loop."""
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
