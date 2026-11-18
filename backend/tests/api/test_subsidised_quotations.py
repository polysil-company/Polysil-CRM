"""FS-057: a subsidised quotation carries the calculator's answer, prints it, and
becomes a subsidised order with the subsidy filled in."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.schemas.subsidy import CalculateRequest
from tests.api import test_order_endpoints as endpoints
from tests.api import test_subsidy_applications as apps_t
from tests.api.conftest import V1, _key
from tests.api.test_subsidy_applications import Office, _as, _calc, _lead

pytestmark = pytest.mark.db

shop = endpoints.shop
office = apps_t.office
fake_engine = apps_t.fake_engine
Q = f"{V1}/quotations"
Sessions = Callable[[], AsyncSession]


async def _quotation(client: httpx.AsyncClient, o: Office, h: dict[str, str]) -> dict[str, Any]:
    lead = await _lead(client, o, h)
    r = await client.post(Q, headers={**h, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "subsidised",
        "place_of_supply_territory_id": o.shop.district, "seller_gstin_id": o.shop.seller,
        "price_effective_date": endpoints.AS_OF,
        "lines": [{"product_id": o.shop.product, "qty": "20", "discount_pct": "5"}]})
    assert r.status_code == 201, r.text
    data: dict[str, Any] = r.json()["data"]
    return data


async def _put(client: httpx.AsyncClient, h: dict[str, str], qid: str, o: Office,
               category: str = "small_farmer", **calc: Any) -> httpx.Response:
    return await client.put(f"{Q}/{qid}/subsidy", headers={**h, **_key()},
                            json={"category_code": category, "calculation": {**_calc(o), **calc}})


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


async def test_a_subsidised_quotation_carries_its_subsidy_to_the_order(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest]) -> None:
    fo = await _as(client, office, "field_officer")
    q = await _quotation(client, office, fo)
    assert q["sales_type"] == "subsidised" and q["subsidy"] is None

    r = await client.post(f"{Q}/{q['id']}/send", headers={**fo, **_key()}, json={"channel": "none"})
    assert r.status_code == 422 and _code(r) == "subsidy_missing", "rule 5"

    r = await _put(client, fo, q["id"], office)
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    s = got["subsidy"]
    assert (s["scheme"], s["subsidy"], s["farmer_share"]) == ("GGRC", "70000.50", "17500.25")
    assert s["category"]["code"] == "small_farmer" and s["total_cost"] == "95000.75"
    assert fake_engine[-1].scheme == "GGRC", "B-3: no scheme sent, the lead's used"
    assert any(w.startswith("calculation_total_differs") for w in got["warnings"]), "rule 4"

    r = await _put(client, fo, q["id"], office, category="general")
    assert r.status_code == 422 and "category_code" in r.json()["error"]["fields"], "applies on every crop"
    r = await _put(client, fo, q["id"], office, scheme="CG")
    assert r.status_code == 422 and "calculation.scheme" in r.json()["error"]["fields"], "an explicit other scheme"
    r = await _put(client, fo, q["id"], office, system_type="sprinkler")
    assert r.status_code == 422 and "calculation.system_type" in r.json()["error"]["fields"], "EC-7"

    r = await client.patch(f"{Q}/{q['id']}", headers={**fo, **_key()}, json={"sales_type": "commercial"})
    assert r.status_code == 422 and _code(r) == "subsidy_block_exists", "S-5"

    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{Q}/{q['id']}/{path}", headers={**fo, **_key()}, json=body)
        assert r.status_code == 200, r.text
    r = await _put(client, fo, q["id"], office)
    assert r.status_code == 409 and _code(r) == "quotation_not_draft"
    full = (await client.get(f"{Q}/{q['id']}/subsidy/calculation", headers=fo)).json()["data"]
    assert len(full["crops"]) == 2

    # rule 8: refusals first, then the order
    r = await client.post(f"{V1}/orders", headers={**fo, **_key()}, json={
        "order_type": "subsidised", "quotation_ids": [q["id"]],
        "subsidy": {"lead_ids": [q["lead"]["id"]], "subsidy_amount": "1.00"}})
    assert r.status_code == 422 and _code(r) == "subsidy_from_quotation", r.text
    r = await client.post(f"{V1}/orders", headers={**fo, **_key()}, json={"quotation_ids": [q["id"]]})
    assert r.status_code == 422 and _code(r) == "type_mismatch", "a commercial order from it is refused"
    order = await endpoints._create(client, fo, {"order_type": "subsidised", "quotation_ids": [q["id"]]})
    block = order["subsidy"]
    assert (block["material_amount"], block["subsidy_amount"], block["farmer_payable"]) == \
        ("95000.75", "70000.50", "17500.25")
    assert [x["id"] for x in block["leads"]] == [q["lead"]["id"]]
    assert order["lead"]["id"] == q["lead"]["id"]


async def test_a_revision_carries_the_block(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest]) -> None:
    fo = await _as(client, office, "field_officer")
    q = await _quotation(client, office, fo)
    assert (await _put(client, fo, q["id"], office)).status_code == 200
    r = await client.post(f"{Q}/{q['id']}/send", headers={**fo, **_key()}, json={"channel": "none"})
    assert r.status_code == 200, r.text
    r = await client.post(f"{Q}/{q['id']}/revise", headers={**fo, **_key()},
                          json={"price_effective_date": endpoints.AS_OF})
    assert r.status_code == 201, r.text
    rev = r.json()["data"]
    assert rev["version"] == 2 and rev["subsidy"] is not None
    assert rev["subsidy"]["subsidy"] == "70000.50", "rule 6"


async def test_a_commercial_quotation_takes_no_subsidy(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest]) -> None:
    fo = await _as(client, office, "field_officer")
    q = await _quotation(client, office, fo)
    r = await client.patch(f"{Q}/{q['id']}", headers={**fo, **_key()}, json={"sales_type": "commercial"})
    assert r.status_code == 200, r.text
    r = await _put(client, fo, q["id"], office)
    assert r.status_code == 422 and _code(r) == "not_subsidised", r.text


async def _sent_with_block(client: httpx.AsyncClient, o: Office, h: dict[str, str]) -> dict[str, Any]:
    q = await _quotation(client, o, h)
    assert (await _put(client, h, q["id"], o)).status_code == 200
    r = await client.post(f"{Q}/{q['id']}/send", headers={**h, **_key()}, json={"channel": "none"})
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()["data"]
    return data


async def test_the_farmers_link_shows_the_subsidy(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest],
        sessions: Sessions) -> None:
    """Code review F-1, rule 7: the public view's subsidy reaches the link."""
    fo = await _as(client, office, "field_officer")
    q = await _sent_with_block(client, office, fo)
    s = sessions()
    try:
        token = (await s.execute(text("SELECT share_token FROM quotation WHERE id = CAST(:q AS uuid)"),
                                 {"q": q["id"]})).scalar_one()
    finally:
        await s.close()
    body = (await client.get(f"{V1}/public/q/{token}")).json()["data"]
    assert body["subsidy"] == {"scheme": "GGRC", "category": "Small Farmer", "total_cost": "95000.75",
                               "subsidy": "70000.50", "farmer_share": "17500.25"}, body["subsidy"]


def test_the_public_fields_are_the_schemas() -> None:
    """Code review F-1: PUBLIC_FIELDS is what the link may carry; the schema is what it does."""
    from api.domain.quotations import PARTY_COLUMNS, PUBLIC_FIELDS
    from api.schemas.quotations import PublicQuotation
    assert set(PublicQuotation.model_fields) == set(PUBLIC_FIELDS)
    assert not set(PUBLIC_FIELDS) & PARTY_COLUMNS


async def test_the_block_is_staff_and_scope_bound(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest],
        sessions: Sessions) -> None:
    """Code review F-2: a role without quotations.edit is refused; a caller outside the
    quotation's scope cannot read the calculation; the definer refuses on its own."""
    fo = await _as(client, office, "field_officer")
    q = await _sent_with_block(client, office, fo)
    stranger = await _as(client, office, "stranger")       # quotations.view, no territory
    r = await _put(client, stranger, q["id"], office)
    assert r.status_code == 403, r.text
    r = await client.get(f"{Q}/{q['id']}/subsidy/calculation", headers=stranger)
    assert r.status_code == 404, "the parent-scoped policy hides it"

    draft = await _quotation(client, office, fo)
    r = await client.patch(f"{Q}/{draft['id']}", headers={**fo, **_key()}, json={"sales_type": "commercial"})
    assert r.status_code == 200, r.text
    s = sessions()
    try:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                        {"u": office.shop.ids["field_officer"]})
        await enter_role(s, "app_role")
        for target, code in ((q["id"], "QSBND"), (draft["id"], "QSBTY")):
            await s.execute(text("SAVEPOINT p"))
            with pytest.raises(DBAPIError) as err:
                await s.execute(text(
                    "SELECT quotation_subsidy_set(CAST(:q AS uuid), 'GGRC', 'drip', 'x', 'x', 1, "
                    "'{}'::jsonb, '{}'::jsonb, 1, 0, 0, 1, 'v', DATE '2020-06-15')"), {"q": target})
            assert getattr(err.value.orig, "sqlstate", None) == code or code in str(err.value)
            await s.execute(text("ROLLBACK TO SAVEPOINT p"))
    finally:
        await s.rollback()
        await s.close()


async def test_a_changed_lead_system_stops_the_send(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest],
        sessions: Sessions) -> None:
    """Code review F-3: the block was calculated for drip; the lead is now sprinkler."""
    fo = await _as(client, office, "field_officer")
    q = await _quotation(client, office, fo)
    assert (await _put(client, fo, q["id"], office)).status_code == 200
    r = await client.patch(f"{V1}/leads/{q['lead']['id']}", headers={**fo, **_key()},
                           json={"mis_system": "sprinkler"})
    assert r.status_code == 200, r.text
    r = await client.post(f"{Q}/{q['id']}/send", headers={**fo, **_key()}, json={"channel": "none"})
    assert r.status_code == 422 and _code(r) == "subsidy_system_changed", r.text


async def test_ap_state_gst_joins_the_orders_subsidy(
        client: httpx.AsyncClient, office: Office, fake_engine: list[CalculateRequest],
        sessions: Sessions) -> None:
    """FS-063 rule 13, EC-6: the order's subsidy is what the government pays, so AP's
    state GST joins it and the farmer is owed his share only."""
    fo = await _as(client, office, "field_officer")
    q = await _quotation(client, office, fo)
    assert (await _put(client, fo, q["id"], office)).status_code == 200
    s = sessions()
    # the stored answer as the AP engine writes it: 1,000.00 of the GST is the state's
    # material 95,000.75 = subsidy 70,000.50 + share 24,000.25 + state GST 1,000.00
    await s.execute(text(
        "UPDATE quotation_subsidy SET calculation = jsonb_set(calculation, "
        "'{total,blocks,gst_paid_by_state}', '\"1000.00\"'), farmer_share = 24000.25 "
        "WHERE quotation_id = CAST(:q AS uuid)"),
        {"q": q["id"]})
    await s.commit()
    await s.close()
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{Q}/{q['id']}/{path}", headers={**fo, **_key()}, json=body)
        assert r.status_code == 200, r.text
    order = await endpoints._create(client, fo, {"order_type": "subsidised", "quotation_ids": [q["id"]]})
    block = order["subsidy"]
    assert (block["subsidy_amount"], block["farmer_payable"]) == ("71000.50", "24000.25")
    assert "farmer_payable_not_material_less_subsidy" not in order.get("warnings", []), order
    got = (await client.get(f"{Q}/{q['id']}", headers=fo)).json()["data"]["subsidy"]
    assert got["gst_paid_by_state"] == "1000.00", "code review F-4: the block shows it"
