"""Two 500s Schemathesis found (27 Oct), each answered as a 4xx now."""

# ruff: noqa: E501  (test names)

from __future__ import annotations

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
