"""Two 500s Schemathesis found (27 Oct), and ISS-229, each answered as a 4xx now."""

# ruff: noqa: E501  (test names)

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop


@pytest.mark.parametrize("url", [
    f"{V1}/lookups/partners?q=%00",
    f"{V1}/leads?q=ab%00cd",
    f"{V1}/lookups/partners?q=%00&limit=5",
    f"{V1}/leads/%00",
])
async def test_a_nul_anywhere_in_the_request_is_a_422_never_a_500(client: httpx.AsyncClient, url: str) -> None:
    """Postgres refuses a NUL in text; the request is refused before it gets there,
    signed in or not."""
    r = await client.get(url)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "invalid_character"


async def test_the_scheme_for_a_lead_checks_the_id_is_a_uuid(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/subsidy-schemes/for-lead/{'0' * 36}", headers=h)
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("field", ["farmer_name", "village", "note"])
async def test_a_nul_inside_a_json_body_is_a_422_never_a_500(client: httpx.AsyncClient, shop: Shop, field: str) -> None:
    """ISS-229: JSON allows \\u0000 in a string; Postgres text does not."""
    h = await endpoints._as(client, shop, "district_manager")
    body = {"farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
            "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"}
    body[field] = "ab\u0000cd"
    r = await client.post(f"{V1}/leads", json=body,
                          headers={**h, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "invalid_character"


async def test_the_text_backslash_u0000_is_not_a_nul_and_saves(client: httpx.AsyncClient, shop: Shop) -> None:
    """An even run of backslashes is a literal backslash, so the guard lets it through."""
    h = await endpoints._as(client, shop, "district_manager")
    r = await client.post(f"{V1}/leads", json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Ward " + chr(92) + "u0000"}, headers={**h, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["village"] == "Ward " + chr(92) + "u0000"
