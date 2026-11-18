"""FS-090 (BE-044): documents above ₹10 crore save, send and submit.

The old ceiling, 99,999,999.99, refused these at the preview and at save. The
catalogue rates are ₹103.19 and ₹100, so a million units clears ₹10 crore.
"""

# ruff: noqa: F811  (the fixtures are imported from the modules that define them)

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

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
CRORE = D("10000000")


async def test_a_ten_crore_quotation_previews_saves_and_sends(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    lines = [_line(catalogue, qty="1000000", discount_pct="0", discount2_pct="0", gst_slab="18")]
    r = await client.post(f"{V1}/pricing/quote-lines", json={
        "place_of_supply_territory_id": catalogue.gujarat_district_id,
        "seller_gstin_id": catalogue.gstin_id, "as_of": AS_OF, "sales_type": "commercial",
        "lines": lines}, headers=h)
    assert r.status_code == 200, r.text
    lead = await _qualified_lead(client, h, qenv)
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()}, json=_create_body(
        lead["id"], catalogue, lines=lines, freight={"amount": "2500000.00"}))
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert D(q["totals"]["gross"]) == D("103190000.00")
    assert D(q["totals"]["total"]) > 12 * CRORE
    sent = await _send(client, h, q["id"])
    assert sent["status"] == "sent"


async def test_a_ten_crore_order_saves_and_submits(client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _shop_as(client, shop, "admin_sales")
    draft = await _create_order(client, ho, _direct(
        shop, lines=[{"product_id": shop.product, "qty": "1000000", "discount_pct": "0",
                      "gst_slab": "18"}],
        freight={"amount": "5000000.00"}))
    assert D(draft["totals"]["gross"]) == 10 * CRORE
    assert draft["totals"]["total"] == "123900000.00"   # (10 crore + 50 lakh) x 1.18
    order = await _submit(client, ho, draft["id"])
    assert order["status"] in ("submitted", "approved")
