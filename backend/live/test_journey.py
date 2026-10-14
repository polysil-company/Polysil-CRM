"""The journey on staging: lead to quotation to PDF to order to document (FS-065 rules 18 to 24).

Written fresh against the real endpoints. The drivers in `scripts/livetest/` use
random real-format mobiles and delete a lead, so none of them is reused here.

What it leaves behind, on purpose (rule 20): one lead, one quotation, one draft
order and one document, every name starting `LIVE-<run id>`, every mobile the one
in `LIVE_TEST_MOBILE`. Staging sends real WhatsApp, so the quotation goes with
`channel: "none"` and the order is never submitted: the one message a run sends is
the lead acknowledgement (rule 19).

The steps run in file order and share one `Run`. A step whose input is missing
skips with the reason the chain stopped, so a missing precondition reads as
`SKIP journey: <reason>` all the way down rather than as a cascade of failures.

Storage has no endpoint of its own to ask, so it is found at the PDF step
(rule 22). A PDF that fails for storage skips the two PDF steps only: accept,
order, upload and the negative cases need no PDF and still run. With
`LIVE_EXPECT_STORAGE=1` a storage failure is a FAIL instead, for a box where
storage is meant to work.

Assertions carry their own messages: the suite runs with `--assert=plain`, so
pytest prints no values, and every message is built from ids, codes, stages and
counts, never a name or a number (rule 27).
"""

from __future__ import annotations

import datetime as dt
import io
import os
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, NoReturn

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from live.client import API, LiveClient, LiveTimeoutError, SignInError
from live.conftest import india_today
from live.guard import (
    GuardError,
    read_health,
    require_journey_allowed,
    require_test_mobile,
    require_usable_account,
)
from live.redact import describe, error_code, redact

TARGET = os.environ.get("LIVE_TARGET", "")
ALLOW_LOCAL = os.environ.get("LIVE_ALLOW_LOCAL") == "1"
EXPECT_STORAGE = os.environ.get("LIVE_EXPECT_STORAGE") == "1"

if TARGET == "production" or (TARGET == "local" and not ALLOW_LOCAL):
    pytest.skip(f"journey: writes, so it runs on staging only, not {TARGET}",
                allow_module_level=True)

PDF_WAIT_SECONDS = 120
PRODUCT_TRIES = 25
# Demo users from scripts/seed_demo.py: a district manager and a field officer.
DISTRICT_MANAGER = "asha@polysil.in"
FIELD_OFFICER = "ravi@polysil.in"
# A GET each, and the module whose `view` it needs. The first one the field
# officer lacks is the 403 case of rule 24.
GATED_READS = (("users", f"{API}/users"), ("pricing", f"{API}/price-lists"),
               ("sales_orders", f"{API}/orders"), ("quotations", f"{API}/quotations"))


@dataclass
class Run:
    run_id: str
    mobile: str
    stopped: str | None = None
    values: dict[str, Any] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        return f"LIVE-{self.run_id}"

    @property
    def digits(self) -> str:
        return "".join(ch for ch in self.mobile if ch.isdigit())[-10:]

    def stop(self, reason: str) -> NoReturn:
        """A precondition is missing: skip this step and every one after it."""
        self.stopped = reason
        pytest.skip(f"journey: {reason}")

    def need(self, *keys: str) -> tuple[Any, ...]:
        if self.stopped:
            pytest.skip(f"journey: {self.stopped}")
        missing = [k for k in keys if k not in self.values]
        if missing:
            pytest.skip(f"journey: an earlier step did not finish ({', '.join(missing)})")
        return tuple(self.values[k] for k in keys)


def inr(amount: str) -> str:
    """`1856.5` as the PDF prints it, `1,856.50`; lakhs grouped in twos."""
    whole, _, paise = f"{Decimal(amount):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([*groups, tail]) + "." + paise


def quantity(pack_multiple: str | None) -> str:
    """One pack, written with no more decimals than it needs: `100.000` is refused
    on a unit that admits none."""
    if not pack_multiple:
        return "1"
    value = Decimal(pack_multiple)
    if value == value.to_integral_value():
        return str(value.to_integral_value())
    return format(value.normalize(), "f")


def flat(text: str) -> str:
    return " ".join(text.split())


def data(response: httpx.Response, *expected: int) -> Any:
    """The envelope's `data`, after asserting the status. The failure line is the
    path, the status and the code only (rule 27)."""
    assert response.status_code in expected, describe(response)
    return response.json()["data"]


def storage_missing(run: Run, where: str) -> NoReturn:
    """Storage is not there. A FAIL where it is expected; otherwise a skip of this
    step alone, never `run.stop`: the steps after the PDF do not need it (code
    review F4)."""
    if EXPECT_STORAGE:
        pytest.fail(f"storage failed at {where}, and LIVE_EXPECT_STORAGE is set")
    run.values["storage_missing"] = where
    pytest.skip(f"journey: storage not configured on this box ({where})")


def no_seller_registration(response: httpx.Response) -> bool:
    """The preview's missing-GSTIN answer is a plain `not_found`; its message is
    what tells it from a route that has gone (code review F4). Read, never printed."""
    if response.status_code != 404 or error_code(response) != "not_found":
        return False
    try:
        message = str(response.json()["error"].get("message", ""))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False
    return "seller registration" in message.lower()


def in_force(price_list: dict[str, Any], today: dt.date) -> bool:
    starts = dt.date.fromisoformat(price_list["effective_from"])
    ends = price_list.get("effective_to")
    return (price_list.get("is_active", True) and starts <= today
            and (ends is None or dt.date.fromisoformat(ends) > today))


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def run() -> Run:
    try:
        mobile = require_test_mobile(os.environ)
    except GuardError as exc:
        pytest.fail(str(exc))
    return Run(run_id=uuid.uuid4().hex[:6], mobile=mobile)


@pytest.fixture(scope="module")
def writer(signed_in: LiveClient, me: dict[str, Any], run: Run) -> LiveClient:
    """The same sign-in, allowed to write, after the box proves it is staging."""
    try:
        require_journey_allowed(signed_in, allow_local=ALLOW_LOCAL)
    except (GuardError, LiveTimeoutError) as exc:
        pytest.fail(str(exc))
    return signed_in.writer()


def demo_client(signed_in: LiveClient, email: str) -> LiveClient:
    """A read-only client signed in as a demo user. Its sign-in and sign-out join
    the run's list of non-GET requests."""
    password = os.environ.get("DEMO_PASSWORD", "")
    if not password:
        pytest.skip("journey: DEMO_PASSWORD is not set, so the demo users cannot sign in")
    demo = LiveClient(signed_in.base_url, signed_in.environment, read_only=True,
                      deadline=signed_in.deadline)
    demo.writes = signed_in.writes
    try:
        demo.login(email, password)
    except (SignInError, LiveTimeoutError) as exc:
        demo.close()
        pytest.fail(f"demo sign-in failed, not retried: {exc}")
    return demo


def close_demo(demo: LiveClient) -> None:
    try:
        demo.logout()
    finally:
        demo.close()


# ── the path of rule 21 ─────────────────────────────────────────────────────

def test_preconditions(writer: LiveClient, run: Run) -> None:
    """Territories and MIS systems, and the preconditions of rule 22: a seller
    GSTIN in force and a price list for the lead's state. Storage has no read of
    its own; the PDF and the upload steps report it where it is first used."""
    gstins = data(writer.get(f"{API}/seller-gstins"), 200)
    if not any(g.get("is_active") for g in gstins):
        run.stop("no seller GSTIN in force")

    systems = data(writer.get(f"{API}/lookups/mis-systems"), 200)
    active = [s["code"] for s in systems if s.get("is_active", True)]
    if not active:
        run.stop("no MIS system to put on a lead")

    today = india_today()
    lists = data(writer.get(f"{API}/price-lists", params={"status": "published", "limit": "100"}),
                 200)
    usable = [p for p in lists if in_force(p, today)
              and p.get("channel_tier") in (None, "farmer")]
    everywhere = any(p.get("state_territory") is None for p in usable)
    states = {p["state_territory"]["id"] for p in usable if p.get("state_territory")}

    districts = data(writer.get(f"{API}/lookups/territories",
                                params={"level": "district", "limit": "100"}), 200)
    for district in districts:
        state = (district.get("parent") or {}).get("id")
        if everywhere or state in states:
            run.values.update(territory_id=district["id"], state_id=state, mis_system=active[0])
            return
    run.stop("no price list in force for any district's state")


def test_create_lead(writer: LiveClient, run: Run) -> None:
    territory_id, mis_system = run.need("territory_id", "mis_system")
    # Read again just before the first write (rule 18).
    require_journey_allowed(writer, allow_local=ALLOW_LOCAL)
    lead = data(writer.post(f"{API}/leads", json={
        "farmer_name": f"{run.prefix} Farmer",
        "mobile": run.mobile,
        "territory_id": territory_id,
        "inquiry_type": "commercial",
        "mis_system": mis_system,
        "note": f"{run.prefix}: live check journey, safe to ignore",
    }), 201)
    run.values["lead_id"] = lead["id"]
    run.values["lead_org_unit"] = lead["owner_org_unit"]["id"]
    assert lead["farmer_name"].startswith(run.prefix), "the lead's name lost its LIVE- prefix"
    assert lead["mobile"].endswith(run.digits), "the lead's mobile is not LIVE_TEST_MOBILE"
    assert lead["stage"] == "new", f"a new lead is at stage {lead['stage']}"
    # Every run's lead shares the mobile, so the duplicate list grows run by run
    # (rule 23). Nothing about how many: each listed duplicate is another lead.
    for duplicate in lead["duplicates"]:
        assert duplicate["lead_id"] and duplicate["lead_id"] != lead["id"], \
            f"lead {lead['id']} lists itself or a blank id as its duplicate"

    found = data(writer.get(f"{API}/leads", params={"q": run.prefix}), 200)
    assert lead["id"] in [row["id"] for row in found], \
        f"lead {lead['id']} is not found by its own name"


def test_contacted_then_qualified(writer: LiveClient, run: Run) -> None:
    (lead_id,) = run.need("lead_id")
    for stage in ("contacted", "qualified"):
        lead = data(writer.post(f"{API}/leads/{lead_id}/transition", json={"to_stage": stage}),
                    200)
        assert lead["id"] == lead_id and lead["stage"] == stage, \
            f"lead {lead_id} is at {lead['stage']} after a move to {stage}"


def test_preview_two_products(writer: LiveClient, run: Run) -> None:
    _, territory_id = run.need("lead_id", "territory_id")
    products = data(writer.get(f"{API}/products", params={"active": "true", "limit": "100"}), 200)
    candidates = [p for p in products if p.get("hsn_code") and p.get("gst_slab")]
    preview = f"{API}/pricing/quote-lines"

    priced: list[dict[str, str]] = []
    for product in candidates[:PRODUCT_TRIES]:
        line = {"product_id": product["id"], "qty": quantity(product.get("pack_multiple"))}
        response = writer.post(preview, json={"place_of_supply_territory_id": territory_id,
                                              "lines": [line], "sales_type": "commercial"})
        if response.status_code == 200:
            priced.append(line)
            if len(priced) == 2:
                break
        elif no_seller_registration(response):
            run.stop("no seller GSTIN in force (the preview said so)")
        elif error_code(response) not in ("product_not_priced", "product_missing_tax_rate",
                                          "product_inactive"):
            pytest.fail(describe(response))
    if len(priced) < 2:
        run.stop("fewer than two products priced for the lead's state")

    quote = data(writer.post(preview, json={"place_of_supply_territory_id": territory_id,
                                            "lines": priced, "sales_type": "commercial"}), 200)
    assert len(quote["lines"]) == 2, f"the preview priced {len(quote['lines'])} lines of 2"
    assert Decimal(quote["totals"]["total"]) > 0, "the preview's total is not positive"
    sent_qty = {ln["product_id"]: ln["qty"] for ln in priced}
    run.values["lines"] = [
        {"product_id": ln["product_id"], "qty": sent_qty[ln["product_id"]], "discount_pct": "0",
         "price_list_item_id": ln["price_list_item_id"], "gst_rate_id": ln["gst_rate_id"]}
        for ln in quote["lines"]]
    run.values["preview_total"] = quote["totals"]["total"]


def test_create_quotation(writer: LiveClient, run: Run) -> None:
    lead_id, lines, preview_total = run.need("lead_id", "lines", "preview_total")
    quotation = data(writer.post(f"{API}/quotations", json={"lead_id": lead_id, "lines": lines}),
                     201)
    run.values["quotation_id"] = quotation["id"]
    assert quotation["status"] == "draft" and quotation["quote_no"] is None, \
        f"a new quotation is {quotation['status']}, numbered: {bool(quotation['quote_no'])}"
    assert len(quotation["lines"]) == 2, f"the quotation has {len(quotation['lines'])} lines"
    assert all(Decimal(ln["discount_pct"]) == 0 for ln in quotation["lines"]), \
        "a line carries a discount the journey did not send"
    assert Decimal(quotation["totals"]["total"]) == Decimal(preview_total), \
        f"saved total {quotation['totals']['total']} differs from the preview's {preview_total}"
    assert quotation["party"]["name"].startswith(run.prefix), "the party name is not the lead's"
    assert quotation["party"]["mobile"].endswith(run.digits), \
        "the party mobile is not LIVE_TEST_MOBILE"


def test_send_without_a_message(writer: LiveClient, run: Run) -> None:
    lead_id, quotation_id = run.need("lead_id", "quotation_id")
    quotation = data(writer.post(f"{API}/quotations/{quotation_id}/send",
                                 json={"channel": "none"}), 200)
    assert quotation["status"] == "sent" and quotation["quote_no"], \
        f"after send the quotation is {quotation['status']}"
    run.values["quote_no"] = quotation["quote_no"]
    lead = data(writer.get(f"{API}/leads/{lead_id}"), 200)
    assert lead["stage"] == "quoted", f"after send the lead is at {lead['stage']}"


def test_pdf_becomes_ready(writer: LiveClient, run: Run) -> None:
    quotation_id, _ = run.need("quotation_id", "quote_no")
    waited_until = time.monotonic() + PDF_WAIT_SECONDS
    while True:
        quotation = data(writer.get(f"{API}/quotations/{quotation_id}"), 200)
        if quotation["pdf_state"] == "ready":
            run.values["quotation"] = quotation
            return
        if quotation["pdf_state"] == "failed":
            reason = redact(quotation.get("pdf_error") or "no reason given")
            if "storage" in reason.lower():
                storage_missing(run, "the PDF render")
            pytest.fail(f"the PDF failed to render: {reason}")
        if time.monotonic() > waited_until:
            pytest.fail(f"pdf_state still {quotation['pdf_state']} after {PDF_WAIT_SECONDS} s")
        time.sleep(2)


def test_pdf_contents(writer: LiveClient, run: Run) -> None:
    quotation_id, quotation = run.need("quotation_id", "quotation")
    response = writer.get(f"{API}/quotations/{quotation_id}/pdf")
    if response.status_code == 409 and error_code(response) == "storage_unavailable":
        storage_missing(run, "the PDF link")
    link = data(response, 200)
    # The signed link is the credential; the bearer token must not travel with it.
    pdf = writer.get(link["url"], auth=False)
    assert pdf.status_code == 200, f"the signed PDF link answered {pdf.status_code}"
    assert pdf.content.startswith(b"%PDF"), "the signed link did not return a PDF"

    reader = PdfReader(io.BytesIO(pdf.content))
    assert len(reader.pages) > 1, "the company profile pages are missing"
    first = reader.pages[0]
    width, height = float(first.mediabox.width), float(first.mediabox.height)
    if first.rotation % 180:
        width, height = height, width
    assert width < height, "page 1 is not portrait"

    page_one = flat(first.extract_text() or "")
    assert "quotation" in page_one.lower(), "no title on page 1"
    assert quotation["quote_no"] in page_one, "the quotation number is not on page 1"
    assert inr(quotation["totals"]["total"]) in page_one, "the total is not on page 1"
    if quotation["is_provisional"]:
        assert "INDICATIVE PRICING" in page_one.upper(), "stand-in prices carry no banner"


def test_accept(writer: LiveClient, run: Run) -> None:
    lead_id, quotation_id, _ = run.need("lead_id", "quotation_id", "quote_no")
    quotation = data(writer.post(f"{API}/quotations/{quotation_id}/transition",
                                 json={"to": "accepted"}), 200)
    assert quotation["status"] == "accepted", f"after accept it is {quotation['status']}"
    run.values["accepted"] = True
    lead = data(writer.get(f"{API}/leads/{lead_id}"), 200)
    assert lead["stage"] == "won", f"after accept the lead is at {lead['stage']}"


def test_order_from_quotation(writer: LiveClient, run: Run) -> None:
    lead_id, quotation_id, _ = run.need("lead_id", "quotation_id", "accepted")
    order = data(writer.post(f"{API}/orders", json={"quotation_ids": [quotation_id]}), 201)
    run.values["order_id"] = order["id"]
    # A draft: never submitted, so no approval message goes out (rule 19).
    assert order["status"] == "draft" and order["order_no"] is None, \
        f"a new order is {order['status']}"
    assert order["lead"]["id"] == lead_id, f"order {order['id']} carries another lead"
    assert quotation_id in [q["id"] for q in order["quotations"]], \
        f"order {order['id']} does not carry quotation {quotation_id}"


def test_upload_document(writer: LiveClient, run: Run) -> None:
    (lead_id,) = run.need("lead_id")
    blank = PdfWriter()
    blank.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    blank.write(buffer)
    response = writer.post(
        f"{API}/documents",
        data={"record_type": "lead", "record_id": lead_id, "doc_type": "other",
              "name": f"{run.prefix} upload"},
        files={"file": (f"{run.prefix}.pdf", buffer.getvalue(), "application/pdf")})
    if response.status_code == 503 and error_code(response) == "storage_unavailable":
        storage_missing(run, "the upload")
    document = data(response, 201)
    run.values["document_id"] = document["id"]
    assert document["record_id"] == lead_id, f"document {document['id']} is on another record"
    assert document["name"].startswith(run.prefix), "the document's name lost its prefix"


def test_timelines_and_documents(writer: LiveClient, run: Run) -> None:
    lead_id, quotation_id, order_id = run.need("lead_id", "quotation_id", "order_id")
    lead_kinds = {e["kind"] for e in data(writer.get(f"{API}/leads/{lead_id}/timeline"), 200)}
    assert {"lead.created", "lead.stage_changed"} <= lead_kinds, sorted(lead_kinds)

    quotation_kinds = {e["kind"] for e in
                       data(writer.get(f"{API}/quotations/{quotation_id}/timeline"), 200)}
    assert {"quotation.created", "quotation.sent", "quotation.accepted"} <= quotation_kinds, \
        sorted(quotation_kinds)

    order_kinds = {e["kind"] for e in data(writer.get(f"{API}/orders/{order_id}/timeline"), 200)}
    assert "order.created" in order_kinds, sorted(order_kinds)

    documents = data(writer.get(f"{API}/leads/{lead_id}/documents"), 200)
    if "document_id" in run.values:
        assert run.values["document_id"] in [d["id"] for d in documents], \
            f"document {run.values['document_id']} is not listed on lead {lead_id}"


# ── the negative cases of rule 24 ───────────────────────────────────────────

def test_other_district_reads_no_lead(signed_in: LiveClient, run: Run) -> None:
    """The district manager of Rajkot cannot read the journey's lead, which is
    owned by the check account's office."""
    lead_id, lead_org_unit = run.need("lead_id", "lead_org_unit")
    demo = demo_client(signed_in, DISTRICT_MANAGER)
    try:
        manager = require_usable_account(demo)
        if (manager.get("org_unit") or {}).get("id") == lead_org_unit:
            pytest.skip("journey: the check account sits in the demo district, so the "
                        "lead is in scope for its manager")
        response = demo.get(f"{API}/leads/{lead_id}")
        assert response.status_code == 404, describe(response)
        listed = data(demo.get(f"{API}/leads", params={"q": run.prefix}), 200)
        assert lead_id not in [row["id"] for row in listed], \
            f"the district manager's list shows lead {lead_id}"
    finally:
        close_demo(demo)


def test_role_without_permission_gets_403(signed_in: LiveClient, run: Run) -> None:
    """403 `insufficient_permission`, not an empty list, for a read the role lacks."""
    run.need("lead_id")
    demo = demo_client(signed_in, FIELD_OFFICER)
    try:
        held = {p["module"] for p in require_usable_account(demo).get("permissions", [])
                if "view" in p.get("actions", [])}
        gated = next(((m, p) for m, p in GATED_READS if m not in held), None)
        if gated is None:
            pytest.skip("journey: the field officer holds view on every gated read listed")
        response = demo.get(gated[1])
        assert response.status_code == 403, describe(response)
        assert error_code(response) == "insufficient_permission", describe(response)
    finally:
        close_demo(demo)


def test_dealer_cannot_read_staff_lead(writer: LiveClient, run: Run) -> None:
    run.need("lead_id")
    provider = read_health(writer).get("whatsapp")
    if provider != "mock":
        pytest.skip(f"journey: the dealer case needs an OTP sign-in, and staging's WhatsApp "
                    f"provider is {provider!r}, not mock")
    pytest.skip("journey: with the mock provider the OTP is readable only from the "
                "database, which the live suite does not reach")
