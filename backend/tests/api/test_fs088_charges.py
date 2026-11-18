"""FS-088 end to end: installation and fittings charges beside freight, on
quotations and orders.

Figures: the quotation line's taxable value is 1,588.10 at 5 % (1,667.50 with tax);
the order line's is 900.00 at 5 % (945.00). Installation defaults to 18 %,
fittings to the goods' 5 %.
"""

# ruff: noqa: F811  (the fixtures are imported from the modules that define them)

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import V1, Catalogue, Staff, _auth, _key
from tests.api.test_gst_choice_freight import _draft
from tests.api.test_order_endpoints import (  # noqa: F401
    Shop,
    _accepted_quotation,
    _direct,
    _submit,
    shop,
)
from tests.api.test_order_endpoints import _as as _shop_as
from tests.api.test_order_endpoints import _create as _create_order
from tests.api.test_quotation_endpoints import (  # noqa: F401  (the fixtures)
    AS_OF,
    QEnv,
    _send,
    qenv,
    quoter,
)

pytestmark = pytest.mark.db

D = Decimal
THREE = {"freight": {"amount": "500.00"}, "installation": {"amount": "1000.00"},
         "fittings": {"amount": "200.00"}}


def _identity(t: dict[str, str]) -> None:
    assert D(t["taxable"]) == (D(t["gross"]) - D(t["discount"]) + D(t["freight"])
                               + D(t["installation"]) + D(t["fittings"]))


async def test_three_charges_each_taxed_and_each_in_its_own_total(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, **THREE)
    i, f = q["installation"], q["fittings"]
    assert (D(i["gst_slab"]), i["gst_slab_chosen"], i["cgst"], i["total"]) == (
        D(18), False, "90.00", "1180.00"), "installation defaults to 18 %"
    assert (D(f["gst_slab"]), f["total"]) == (D(5), "210.00"), "fittings follow the goods"
    t = q["totals"]
    # EC-1: each charge from its own column, not one derived figure
    assert (t["freight"], t["installation"], t["fittings"]) == ("500.00", "1000.00", "200.00")
    assert t["taxable"] == "3288.10" and t["total"] == "3582.50"
    _identity(t)


async def test_the_list_carries_each_charge_too(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, installation={"amount": "1000.00"})
    r = await client.get(f"{V1}/quotations", params={"q": q["quote_no"]}, headers=h)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["id"] == q["id"])
    assert (row["totals"]["freight"], row["totals"]["installation"]) == ("0.00", "1000.00")


async def test_patch_omit_keeps_null_removes_one_charge_only(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, **THREE)
    r = await client.patch(f"{V1}/quotations/{q['id']}",
                           json={"installation": None, "fittings": {"amount": "300.00",
                                                                    "gst_slab": "18"}},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["installation"] is None and out["freight"]["amount"] == "500.00"
    assert (out["fittings"]["amount"], out["fittings"]["gst_slab_chosen"]) == ("300.00", True)
    assert out["totals"]["installation"] == "0.00"
    _identity(out["totals"])


async def test_saving_the_basket_keeps_every_charge(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    from tests.api.test_quotation_endpoints import _line
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, **THREE)
    r = await client.put(f"{V1}/quotations/{q['id']}/lines",
                         json={"lines": [_line(catalogue, qty="20")]}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert [out[k]["amount"] for k in ("freight", "installation", "fittings")] == [
        "500.00", "1000.00", "200.00"]


async def test_a_type_without_charges_clears_installation_alone(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """EC-3: installation only, no freight, moved to subsidised: 200, not a 500."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, installation={"amount": "1000.00"})
    r = await client.patch(f"{V1}/quotations/{q['id']}",
                           json={"sales_type": "subsidised", "installation": {"amount": "1.00"}},
                           headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "charge_not_allowed", r.text
    assert "installation" in r.json()["error"]["fields"]
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"sales_type": "subsidised"},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["installation"] is None and out["totals"]["installation"] == "0.00"
    assert any(w.startswith("gst_choice_cleared:") for w in out["warnings"])


async def test_a_bad_amount_names_the_charge(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    from tests.api.test_gst_choice_freight import _quote
    h = await _auth(client, quoter)
    r = await _quote(client, h, qenv, catalogue, fittings={"amount": "0.00"})
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "charge_amount_invalid" and "fittings.amount" in err["fields"]


async def test_charges_send_without_a_conflict_and_revise_whole(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, **THREE)
    sent = await _send(client, h, q["id"])
    assert sent["status"] == "sent" and sent["totals"]["total"] == "3582.50"
    token = sent["share_url"].rsplit("/", 1)[1]
    pub = (await client.get(f"{V1}/public/q/{token}")).json()["data"]
    # plan review B-1: the public page reads each charge, not one derived figure
    assert (pub["totals"]["freight"], pub["totals"]["installation"],
            pub["totals"]["fittings"]) == ("500.00", "1000.00", "200.00")
    r = await client.post(f"{V1}/quotations/{q['id']}/revise",
                          json={"price_effective_date": AS_OF}, headers={**h, **_key()})
    assert r.status_code in (200, 201), r.text
    v2 = r.json()["data"]
    assert (v2["installation"]["amount"], v2["fittings"]["amount"]) == ("1000.00", "200.00")


async def test_the_preview_prices_the_charges(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    from tests.api.test_quotation_endpoints import _line
    h = await _auth(client, quoter)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h, json={
        "place_of_supply_territory_id": catalogue.gujarat_district_id,
        "seller_gstin_id": catalogue.gstin_id,
        "as_of": AS_OF, "sales_type": "commercial", "lines": [_line(catalogue)],
        "installation": {"amount": "1000.00"}})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["installation"]["total"] == "1180.00" and out["fittings"] is None
    assert (out["totals"]["installation"], out["totals"]["freight"]) == ("1000.00", "0.00")


# ── orders ───────────────────────────────────────────────────────────────────

async def test_an_order_carries_installation_through_submit(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, installation={"amount": "100.00"}))
    assert draft["installation"]["cgst"] == "9.00"
    assert draft["totals"]["installation"] == "100.00" and draft["totals"]["freight"] == "0.00"
    assert draft["totals"]["total"] == "1063.00"      # 900 + 45 + 100 + 18
    order = await _submit(client, ho, draft["id"])
    assert order["status"] == "submitted" and order["totals"]["total"] == "1063.00"


async def test_a_sample_order_takes_no_fittings(client: httpx.AsyncClient, shop: Shop) -> None:
    hs = await _shop_as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/orders", json=_direct(shop, order_type="sample",
                                                       fittings={"amount": "100.00"}),
                          headers={**hs, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "charge_not_allowed", r.text


async def test_an_order_with_installation_only_moves_to_sample(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-3 on the order: the figures are cleared before the type moves."""
    hs = await _shop_as(client, shop, "admin_sales")
    draft = await _create_order(client, hs, _direct(shop, installation={"amount": "100.00"}))
    r = await client.patch(f"{V1}/orders/{draft['id']}", json={"order_type": "sample"},
                           headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["installation"] is None and out["totals"]["installation"] == "0.00"
    assert any(w.startswith("gst_choice_cleared:") for w in out["warnings"])


async def _accepted_with_charges(client: httpx.AsyncClient, shop: Shop,
                                 h: dict[str, str]) -> dict:
    """_accepted_quotation, with installation and fittings on the quotation."""
    lead = (await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial", "partner_id": None,
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "5"}],
        "installation": {"amount": "300.00"}, "fittings": {"amount": "120.00", "gst_slab": "18"}})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body,
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_an_order_from_a_quotation_takes_its_charges_and_a_body_replaces_one(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Rule 8 end to end: the quotation's charges come with it, the chosen slab too;
    a charge in the body replaces the quotation's."""
    ho = await _shop_as(client, shop, "field_officer")
    q = await _accepted_with_charges(client, shop, ho)
    order = await _create_order(client, ho, {"quotation_ids": [q["id"]]})
    assert order["installation"]["amount"] == "300.00"
    assert (order["fittings"]["amount"], D(order["fittings"]["gst_slab"]),
            order["fittings"]["gst_slab_chosen"]) == ("120.00", D(18), True)
    assert order["freight"] is None and order["totals"]["installation"] == "300.00"
    _identity(order["totals"])
    q2 = await _accepted_with_charges(client, shop, ho)
    replaced = await _create_order(client, ho, {"quotation_ids": [q2["id"]],
                                                "installation": {"amount": "250.00"}})
    assert replaced["installation"]["amount"] == "250.00"
    assert replaced["fittings"]["amount"] == "120.00", "the other charge still comes along"


async def test_a_charge_moved_under_the_draft_is_a_conflict_at_send(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 9: send compares each charge's figures, not freight's alone."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, installation={"amount": "1000.00"})
    s = sessions()
    await s.execute(text(
        "UPDATE quotation SET installation_cgst = installation_cgst + 1, "
        "installation_sgst = installation_sgst - 1 WHERE id = CAST(:q AS uuid)"), {"q": q["id"]})
    await s.commit()
    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**h, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "rate_changed", r.text
    assert "installation" in r.json()["error"]["fields"], r.text
