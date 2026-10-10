"""Orders and the channel (FS-011 4, rule 2, question 15.14, cross-vendor C-1).

A dealer's consolidated order, built over the API by the field officer who raised
the quotations; and what a dealer reads of an order a manager returned. Partner
users sign in by WhatsApp code, so the dealer's reads run through the service
under the dealer's own claim, which is what the router would pass it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.db.session import enter_role
from api.domain.orders import PORTAL_REMARK
from api.errors import ConflictError
from api.services import leads as lead_service
from api.services import orders as service
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

shop = endpoints.shop
Shop = endpoints.Shop

pytestmark = pytest.mark.db

Sessions = Callable[[], AsyncSession]


async def test_quotations_on_two_leads_of_one_dealer_make_one_order_with_the_dealer_as_party(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Rule 2, C-1: no single lead, so the order has none and the dealer is the
    buyer of record; the lines come from both quotations."""
    ho = await endpoints._as(client, shop, "field_officer")
    first = await endpoints._accepted_quotation(client, shop, ho, shop.partner)
    second = await endpoints._accepted_quotation(client, shop, ho, shop.partner)
    assert first["lead"]["id"] != second["lead"]["id"]
    order = await endpoints._create(client, ho, {"quotation_ids": [first["id"], second["id"]]})
    assert order["lead"] is None
    assert order["partner"]["id"] == shop.partner
    assert order["party"]["name"] == "Shah Irrigation"
    assert order["owner"]["id"] == shop.ids["field_officer"]
    assert len(order["lines"]) == 2 and {x["rate"] for x in order["lines"]} == {"90.00"}
    assert sorted(q["id"] for q in order["quotations"]) == sorted([first["id"], second["id"]])


async def test_quotations_on_two_leads_without_a_partner_are_refused(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    first = await endpoints._accepted_quotation(client, shop, ho)
    second = await endpoints._accepted_quotation(client, shop, ho)
    r = await client.post(f"{V1}/orders", json={"quotation_ids": [first["id"], second["id"]]},
                          headers={**ho, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "partner_required", r.text


async def _as_dealer(sessions: Sessions, shop: Shop) -> tuple[AsyncSession, Caller]:
    s = sessions()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                    {"u": shop.ids["dealer"]})
    await enter_role(s, "app_role")
    return s, Caller(shop.ids["dealer"], None, shop.partner,
                     scopes={"sales_orders": "partner_subtree", "leads": "partner_subtree",
                             "dispatch": "partner_subtree"}, user_type="partner_user")


async def test_a_dealer_reads_that_its_order_was_returned_but_not_why_or_by_whom(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Question 15.14 and code review F-2: the step shape a partner gets, the stock
    text in place of the manager's remark, and no decider on any event of the
    order's timeline or of its lead's."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho, shop.partner)
    owner = sessions()
    try:
        # the dealer reads the lead through its assignment
        await owner.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) "
                                 "WHERE id = CAST(:l AS uuid)"),
                            {"p": shop.partner, "l": q["lead"]["id"]})
        await owner.commit()
    finally:
        await owner.close()
    order = await endpoints._submit(client, ho, (await endpoints._create(
        client, ho, {"quotation_ids": [q["id"]]}))["id"])
    hm = await endpoints._as(client, shop, "district_manager")
    remark = "Dealer owes 2 lakh from March"
    r = await endpoints._decide(client, hm, order["approval"]["steps"][0]["id"], "reject", remark)
    assert r.status_code == 200 and r.json()["data"]["last_rejection"]["remark"] == remark, r.text

    s, dealer = await _as_dealer(sessions, shop)
    try:
        seen = await service.get_order(s, dealer, order["id"])
        events = (await service.timeline(s, dealer, order["id"])).data
        on_lead = (await lead_service.timeline(s, dealer, q["lead"]["id"])).data
    finally:
        await s.rollback()
        await s.close()

    assert seen.status == "draft"
    assert seen.last_rejection is not None and seen.last_rejection.remark == PORTAL_REMARK
    assert seen.approval is not None
    for step in seen.approval.steps:
        assert step.by is None and step.remark is None, step
    assert seen.approval.steps[0].decision == "reject"
    for where, evs in (("order", events), ("lead", on_lead)):
        kinds = {e.kind for e in evs}
        assert {"approval.decided", "order.returned"} <= kinds, (where, kinds)
        for e in evs:
            if e.kind in ("approval.decided", "order.returned", "order.approved"):
                assert e.actor is None, (where, e)
        flat = repr([e.model_dump() for e in evs])
        assert remark not in flat, f"the manager's remark reached the dealer's {where} timeline"
        assert shop.ids["district_manager"] not in flat, f"the decider reached the {where} timeline"


async def test_a_dealer_sees_what_shipped_but_not_staff_reasons_or_who_recorded_it(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Code review F-6: void and close-short reasons, and the dispatcher, are
    internal; the quantities and dates are the dealer's to see."""
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(
            client, ho, endpoints._direct(shop, partner_id=shop.partner)))["id"]))
    hd = await endpoints._as(client, shop, "dispatch_manager")
    line = order["lines"][0]["id"]
    sent_at = dt.datetime.now(dt.UTC).isoformat()
    ids = []
    for qty in ("2", "3"):
        r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                              json={"dispatched_at": sent_at,
                                    "lines": [{"order_line_id": line, "qty": qty}]})
        assert r.status_code == 201, r.text
        ids.append(r.json()["data"]["id"])
    void_reason, close_reason = "Wrong truck, dealer disputes", "Dealer has not paid"
    r = await client.post(f"{V1}/dispatches/{ids[0]}/void", json={"remark": void_reason},
                          headers={**hd, **_key()})
    assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/orders/{order['id']}/close-short",
                          json={"remark": close_reason}, headers={**hd, **_key()})
    assert r.status_code == 200 and r.json()["data"]["close_remark"] == close_reason, r.text

    s, dealer = await _as_dealer(sessions, shop)
    try:
        seen = await service.get_order(s, dealer, order["id"])
        on_order = await service.order_dispatches(s, dealer, order["id"])
        listed = (await service.list_dispatches(s, dealer, order_id=order["id"])).data
    finally:
        await s.rollback()
        await s.close()

    assert seen.status == "closed_short" and seen.close_remark is None
    for where, ds in (("detail", seen.dispatches), ("order", on_order), ("list", listed)):
        assert len(ds) == 2, (where, ds)
        for d in ds:
            assert d.dispatched_by is None and d.void_remark is None, (where, d)
            assert d.lines and d.lines[0].order_line_id == line, (where, d)
            # API review B5: a register row opens its order without parsing the number
            assert (d.order.id, d.order.order_no) == (order["id"], seen.order_no), (where, d)
        assert sum(d.voided_at is not None for d in ds) == 1, where
    assert void_reason not in repr(seen) and close_reason not in repr(seen)


async def test_a_dealer_reads_a_rejected_quotation_without_the_staff_remark(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """API review L1: the decision remark is internal, as on orders (question 15.14)."""
    from api.config import get_settings
    from api.services import quotations as quotation_service

    ho = await endpoints._as(client, shop, "field_officer")
    lead = (await client.post(f"{V1}/leads", headers={**ho, **_key()}, json={
        "farmer_name": "Remark Farmer", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod", "assigned_partner_id": shop.partner})).json()["data"]
    for stage in ("contacted", "qualified"):
        await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                          headers={**ho, **_key()})
    r = await client.post(f"{V1}/quotations", headers={**ho, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial", "partner_id": shop.partner,
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": endpoints.AS_OF,
        "lines": [{"product_id": shop.product, "qty": "5", "discount_pct": "0"}]})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                      headers={**ho, **_key()})
    remark = "Dealer margin too thin, do not match competitor"
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**ho, **_key()},
                          json={"to": "rejected", "remark": remark})
    assert r.status_code == 200 and r.json()["data"]["decision_remark"] == remark, r.text

    s, dealer = await _as_dealer(sessions, shop)
    try:
        seen = await quotation_service.get_quotation(s, q["id"], get_settings(),
                                                     portal=dealer.partner_id is not None)
    finally:
        await s.rollback()
        await s.close()
    assert seen.status == "rejected" and seen.decision_remark is None
    assert seen.pdf_error is None


async def test_a_dealer_learns_the_order_pdf_failed_but_not_why(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """FS-012: `pdf_error` names storage and configuration; staff see it, a dealer
    does not."""
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(
            client, ho, endpoints._direct(shop, partner_id=shop.partner)))["id"]))
    reason = "ClientError: NoSuchBucket polysil-internal"
    owner = sessions()
    try:
        await owner.execute(text("UPDATE sales_order SET pdf_state = 'failed', pdf_error = :e "
                                 "WHERE id = CAST(:o AS uuid)"), {"e": reason, "o": order["id"]})
        await owner.commit()
    finally:
        await owner.close()

    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)
    assert r.status_code == 409 and r.json()["error"]["fields"]["pdf_error"] == reason, r.text

    s, dealer = await _as_dealer(sessions, shop)
    try:
        with pytest.raises(ConflictError) as refused:
            await service.pdf_link(s, dealer, order["id"], storage=None)  # type: ignore[arg-type]
    finally:
        await s.rollback()
        await s.close()
    assert refused.value.code == "pdf_failed" and reason not in repr(vars(refused.value))
