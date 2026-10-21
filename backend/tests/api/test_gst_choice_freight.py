"""FS-069 end to end: a GST slab picked per line, and a freight charge, on
quotations and orders.

The catalogue taxes its product at 5 %, so a picked 18 % is always a real choice.
Figures: the quotation line's taxable value is 1,588.10 (18 at 103.19, less 10 %
then 5 %); the order line's is 900.00 (10 at 100.00, less 10 %).
"""

# ruff: noqa: F811  (the fixtures are imported from the modules that define them)

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import V1, Catalogue, Staff, _auth, _key
from tests.api.test_order_endpoints import Shop, _direct, _submit, shop  # noqa: F401  (the fixture)
from tests.api.test_order_endpoints import _as as _shop_as
from tests.api.test_order_endpoints import _create as _create_order
from tests.api.test_quotation_endpoints import (  # noqa: F401  (the fixtures)
    AS_OF,
    QEnv,
    _create_body,
    _line,
    _qualified_lead,
    _send,
    qenv,
    quoter,
)

pytestmark = pytest.mark.db

D = Decimal


async def _quote(client: httpx.AsyncClient, h: dict[str, str], env: QEnv, cat: Catalogue,
                 **over: object) -> httpx.Response:
    lead = await _qualified_lead(client, h, env)
    return await client.post(f"{V1}/quotations", json=_create_body(lead["id"], cat, **over),
                             headers={**h, **_key()})


async def _draft(client: httpx.AsyncClient, h: dict[str, str], env: QEnv, cat: Catalogue,
                 **over: object) -> dict:
    r = await _quote(client, h, env, cat, **over)
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ── the dropdown ─────────────────────────────────────────────────────────────

async def test_the_dropdown_offers_the_admins_slabs(client: httpx.AsyncClient,
                                                    quoter: Staff) -> None:
    h = await _auth(client, quoter)
    r = await client.get(f"{V1}/pricing/gst-slabs", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["choices"] == ["0", "5", "18", "40"]


# ── a chosen line ────────────────────────────────────────────────────────────

async def test_a_picked_slab_taxes_the_line_and_is_marked(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="18")])
    line = q["lines"][0]
    assert line["taxable"] == "1588.10"
    assert (D(line["gst_slab"]), D(line["hsn_slab"]), line["gst_slab_chosen"]) == (
        D(18), D(5), True)
    assert line["cgst"] == line["sgst"] == "142.93"
    assert q["totals"]["total"] == "1873.96"
    assert q["gst_changed_lines"] == 1
    # a chosen slab is the user's, not a stand-in
    assert "gst_slab" not in line["provisional_fields"]


async def test_echoing_the_hsn_slab_is_not_a_choice(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="5.000")])
    assert q["lines"][0]["gst_slab_chosen"] is False and q["gst_changed_lines"] == 0
    assert q["totals"]["total"] == "1667.50"


async def test_a_slab_not_on_the_list_is_refused(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    r = await _quote(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="12")])
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "gst_slab_not_offered" and "lines[0].gst_slab" in err["fields"]


async def test_the_preview_refuses_a_choice_without_a_sales_type(
        client: httpx.AsyncClient, quoter: Staff, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    body = {"place_of_supply_territory_id": catalogue.gujarat_district_id,
            "seller_gstin_id": catalogue.gstin_id, "as_of": AS_OF,
            "lines": [{"product_id": catalogue.product_id, "qty": "18", "gst_slab": "18"}]}
    r = await client.post(f"{V1}/pricing/quote-lines", json=body, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "gst_choice_not_allowed", r.text
    r = await client.post(f"{V1}/pricing/quote-lines", json={**body, "sales_type": "industrial"},
                          headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["gst_slab_chosen"] is True


# ── freight ──────────────────────────────────────────────────────────────────

async def test_freight_defaults_to_the_lines_slab_and_joins_taxable_but_not_gross(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, freight={"amount": "500.00"})
    f = q["freight"]
    assert (f["amount"], D(f["gst_slab"]), f["gst_slab_chosen"]) == ("500.00", D(5), False)
    assert (f["cgst"], f["sgst"], f["total"]) == ("12.50", "12.50", "525.00")
    t = q["totals"]
    assert (t["gross"], t["freight"], t["taxable"]) == ("1857.42", "500.00", "2088.10")
    assert t["total"] == "2192.50"


async def test_freight_follows_a_picked_line_until_its_own_slab_is_picked(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="18")],
                     freight={"amount": "500.00"})
    assert D(q["freight"]["gst_slab"]) == D(18)
    r = await client.patch(f"{V1}/quotations/{q['id']}",
                           json={"freight": {"amount": "500.00", "gst_slab": "5"}},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    f = r.json()["data"]["freight"]
    assert (D(f["gst_slab"]), f["gst_slab_chosen"]) == (D(5), True)


async def test_emptying_the_basket_under_freight_is_refused(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, freight={"amount": "500.00"})
    r = await client.put(f"{V1}/quotations/{q['id']}/lines", json={"lines": []},
                         headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "freight_without_lines", r.text
    r = await client.put(f"{V1}/quotations/{q['id']}/lines",
                         json={"lines": [], "freight": None}, headers={**h, **_key()})
    assert r.status_code == 200, r.text


async def test_saving_the_basket_keeps_freight_and_the_resent_choice(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="18")],
                     freight={"amount": "500.00"})
    r = await client.put(f"{V1}/quotations/{q['id']}/lines",
                         json={"lines": [_line(catalogue, gst_slab="18", qty="20")]},
                         headers={**h, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["lines"][0]["gst_slab_chosen"] is True and out["freight"]["amount"] == "500.00"


# ── the type rule ────────────────────────────────────────────────────────────

async def test_a_type_without_choices_clears_them_with_a_warning(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="18")],
                     freight={"amount": "500.00"})
    r = await client.patch(f"{V1}/quotations/{q['id']}",
                           json={"sales_type": "subsidised", "freight": {"amount": "1.00"}},
                           headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "freight_not_allowed", r.text
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"sales_type": "subsidised"},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["freight"] is None and out["lines"][0]["gst_slab_chosen"] is False
    assert out["totals"]["freight"] == "0.00"
    assert any(w.startswith("gst_choice_cleared:") for w in out["warnings"])


# ── send and revise ──────────────────────────────────────────────────────────

async def test_a_chosen_line_and_freight_send_without_a_conflict_and_revise_whole(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="18")],
                     freight={"amount": "500.00"})
    sent = await _send(client, h, q["id"])
    assert sent["status"] == "sent" and sent["totals"]["total"] == q["totals"]["total"]
    r = await client.post(f"{V1}/quotations/{q['id']}/revise",
                          json={"price_effective_date": AS_OF}, headers={**h, **_key()})
    assert r.status_code == 201 or r.status_code == 200, r.text
    v2 = r.json()["data"]
    assert v2["version"] == 2 and v2["lines"][0]["gst_slab_chosen"] is True
    assert v2["freight"]["amount"] == "500.00"
    assert not any(w.startswith("repriced:") for w in v2["warnings"])


async def test_freight_moved_under_the_draft_is_a_conflict_at_send(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, freight={"amount": "500.00"})
    s = sessions()
    # the stored figures still add up, so only the comparison can catch it
    await s.execute(text("UPDATE quotation SET freight_slab = 18, freight_slab_chosen = true "
                         "WHERE id = CAST(:q AS uuid)"), {"q": q["id"]})
    await s.commit()
    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**h, **_key()})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rate_changed" and "freight" in r.json()["error"]["fields"]


# ── orders ───────────────────────────────────────────────────────────────────

async def test_an_order_carries_a_choice_and_freight_through_submit_to_the_approver(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _shop_as(client, shop, "field_officer")
    body = _direct(shop, lines=[{"product_id": shop.product, "qty": "10", "discount_pct": "10",
                                 "gst_slab": "18"}],
                   freight={"amount": "100.00"})
    draft = await _create_order(client, ho, body)
    line = draft["lines"][0]
    assert (line["taxable"], line["gst_slab_chosen"]) == ("900.00", True)
    assert line["cgst"] == line["sgst"] == "81.00"
    assert draft["freight"]["cgst"] == "9.00", "the default follows the 18 % line"
    assert draft["totals"]["total"] == "1180.00"      # 900 + 162 + 100 + 18
    order = await _submit(client, ho, draft["id"])
    assert order["status"] == "submitted" and order["gst_changed_lines"] == 1
    hd = await _shop_as(client, shop, "district_manager")
    r = await client.get(f"{V1}/approvals/pending", headers=hd)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["document"]["id"] == draft["id"])
    assert row["document"]["gst_changed_lines"] == 1
    assert row["document"]["total"] == "1180.00"


async def test_a_sample_order_takes_no_freight(client: httpx.AsyncClient,
                                               shop: Shop) -> None:
    hs = await _shop_as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/orders", json=_direct(shop, order_type="sample",
                                                       freight={"amount": "100.00"}),
                          headers={**hs, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "freight_not_allowed", r.text


# ── code review F-3, F-1, F-2, F-4 ───────────────────────────────────────────

async def _repoint_tax_row(sessions: Callable[[], AsyncSession], qid: str) -> None:
    """What a moved HSN master looks like to the comparison: the stored line names a
    tax row other than the one that now resolves, with the same rate."""
    s = sessions()
    await s.execute(text(
        "UPDATE quotation_line SET gst_rate_id = (SELECT id FROM gst_rate WHERE hsn_code = '3917' "
        "AND id <> quotation_line.gst_rate_id ORDER BY effective_from DESC LIMIT 1) "
        "WHERE quotation_id = CAST(:q AS uuid)"), {"q": qid})
    await s.commit()


@pytest.mark.parametrize("chosen", [True, False])
async def test_a_moved_hsn_master_conflicts_only_on_an_unchosen_line(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession], chosen: bool) -> None:
    h = await _auth(client, quoter)
    line = _line(catalogue, gst_slab="18") if chosen else _line(catalogue)
    q = await _draft(client, h, qenv, catalogue, lines=[line])
    await _repoint_tax_row(sessions, q["id"])
    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**h, **_key()})
    if chosen:
        assert r.status_code == 200, r.text
    else:
        assert r.status_code == 409 and r.json()["error"]["code"] == "rate_changed", r.text
        assert "lines[0].gst_slab" in r.json()["error"]["fields"]


async def test_a_slab_dropped_from_the_list_stays_on_a_draft_that_holds_it(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="40")])
    s = sessions()
    await s.execute(text("UPDATE app_setting SET value = '[\"0\", \"5\", \"18\"]' "
                         "WHERE key = 'gst_slab_choices'"))
    await s.commit()
    try:
        r = await client.patch(f"{V1}/quotations/{q['id']}",
                               json={"freight": {"amount": "100.00"}}, headers={**h, **_key()})
        assert r.status_code == 200, r.text
        assert D(r.json()["data"]["lines"][0]["gst_slab"]) == D(40)
        r = await _quote(client, h, qenv, catalogue, lines=[_line(catalogue, gst_slab="40")])
        assert r.status_code == 422 and r.json()["error"]["code"] == "gst_slab_not_offered"
    finally:
        s = sessions()
        await s.execute(text("UPDATE app_setting SET value = '[\"0\", \"5\", \"18\", \"40\"]' "
                             "WHERE key = 'gst_slab_choices'"))
        await s.commit()


@pytest.mark.parametrize("amount", ["0", "-5", "10.555", "100000000.00"])
async def test_a_bad_freight_amount_names_its_code(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        amount: str) -> None:
    h = await _auth(client, quoter)
    r = await _quote(client, h, qenv, catalogue, freight={"amount": amount})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "freight_amount_invalid"


async def test_an_order_moved_to_a_sample_drops_its_freight_and_choices(
        client: httpx.AsyncClient, shop: Shop) -> None:
    hs = await _shop_as(client, shop, "admin_sales")
    body = _direct(shop, lines=[{"product_id": shop.product, "qty": "10", "discount_pct": "10",
                                 "gst_slab": "18"}], freight={"amount": "100.00"})
    draft = await _create_order(client, hs, body)
    r = await client.patch(f"{V1}/orders/{draft['id']}", json={"order_type": "sample"},
                           headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["freight"] is None and out["lines"][0]["gst_slab_chosen"] is False
    assert any(w.startswith("gst_choice_cleared:") for w in out["warnings"])
