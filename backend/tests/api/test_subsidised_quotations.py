"""FS-057: a subsidised quotation carries the calculator's answer, prints it, and
becomes a subsidised order with the subsidy filled in."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

from typing import Any

import httpx
import pytest

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
