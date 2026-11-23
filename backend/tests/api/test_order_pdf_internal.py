"""FS-091: the order PDF's internal copy, end to end. An order returned once and
then approved renders both copies; staff get the internal one with every round
and remark, a dealer is refused it; an order rendered before 092 gets its
internal copy without its customer copy changing."""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.errors import ForbiddenError
from api.services import orders as service
from api.storage import LocalStorage
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key, only_these_render
from tests.api.test_order_partners import _as_dealer
from worker.jobs.orders import render_one as render_order

shop = endpoints.shop
Shop = endpoints.Shop

pytestmark = pytest.mark.db

Sessions = Callable[[], AsyncSession]

RETURNED = "Rate below the district floor; re-quote"


async def _returned_then_approved(client: httpx.AsyncClient, shop: Shop) -> dict:
    ho = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, ho, endpoints._direct(
        shop, partner_id=shop.partner, remarks="Deliver before the sowing window"))
    first = await endpoints._submit(client, ho, draft["id"])
    step = first["approval"]["steps"][0]
    r = await endpoints._decide(client, await endpoints._as(client, shop, step["role"]),
                                step["id"], decision="reject", remark=RETURNED)
    assert r.status_code == 200, r.text
    again = await endpoints._submit(client, ho, draft["id"])
    return await endpoints._approve_all(client, shop, again)


async def _render(sessions: Sessions, tmp_path: pathlib.Path, order_id: str) -> str | None:
    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    storage = LocalStorage(root=tmp_path, secret=b"test", public_base="")
    async with only_these_render(sessions, "sales_order", [order_id]):
        return await render_order(settings, storage)


async def _run(sessions: Sessions, sql: str, params: dict) -> None:
    s = sessions()
    try:
        await s.execute(text(sql), params)
        await s.commit()
    finally:
        await s.close()


async def _name(sessions: Sessions, user_id: str) -> str:
    s = sessions()
    try:
        return str((await s.execute(
            text("SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
            {"u": user_id})).scalar_one())
    finally:
        await s.close()


async def test_staff_get_the_internal_copy_with_every_round_and_a_dealer_does_not(
        client: httpx.AsyncClient, shop: Shop, tmp_path: pathlib.Path, sessions: Sessions) -> None:
    order = await _returned_then_approved(client, shop)
    assert await _render(sessions, tmp_path, order["id"]) == "ready"
    ho = await endpoints._as(client, shop, "field_officer")
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]
    assert got["pdf_internal_state"] == "ready"

    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho,
                         params={"copy": "internal"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["filename"] == order["order_no"].replace("/", "-") + "-internal.pdf"
    customer = (await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)).json()["data"]
    assert customer["filename"] == order["order_no"].replace("/", "-") + ".pdf"

    internal = next(tmp_path.rglob(f"orders/{order['id']}/*-internal.pdf")).read_text("utf-8")
    plain = next(f for f in tmp_path.rglob(f"orders/{order['id']}/*.pdf")
                 if not f.name.endswith("-internal.pdf")).read_text("utf-8")
    approver = await _name(sessions, shop.ids[order["approval"]["steps"][0]["role"]])
    for text_ in ("Round 1: Returned for changes", "Round 2: Approved", RETURNED,
                  "Payment seen", "Deliver before the sowing window", approver):
        assert text_ in internal, text_
        assert text_ not in plain, text_

    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho,
                         params={"copy": "draft"})
    assert r.status_code == 422, "only customer and internal"

    s, dealer = await _as_dealer(sessions, shop)
    try:
        with pytest.raises(ForbiddenError):
            await service.pdf_link(s, dealer, order["id"], storage=None,  # type: ignore[arg-type]
                                   internal=True)
        # code review F-6: a dealer reads no internal state either
        seen = await service.get_order(s, dealer, order["id"])
        assert seen.pdf_state == "ready" and seen.pdf_internal_state is None
    finally:
        await s.rollback()
        await s.close()


async def test_an_order_rendered_before_092_gets_its_internal_copy_and_keeps_its_customer_copy(
        client: httpx.AsyncClient, shop: Shop, tmp_path: pathlib.Path, sessions: Sessions) -> None:
    """EC-1: the customer copy, its key and its link do not change."""
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"]))
    await _run(sessions, "UPDATE sales_order SET pdf_state = 'ready', pdf_key = :k, "
                         "pdf_internal_key = NULL, pdf_next_attempt_at = NULL "
                         "WHERE id = CAST(:o AS uuid)",
               {"o": order["id"], "k": f"orders/{order['id']}/old.pdf"})

    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho,
                         params={"copy": "internal"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "pdf_pending", r.text
    assert (await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)).status_code == 200
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]
    assert (got["pdf_state"], got["pdf_internal_state"]) == ("ready", "pending")

    assert await _render(sessions, tmp_path, order["id"]) == "ready"
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]
    assert got["pdf_state"] == "ready"
    s = sessions()
    try:
        row = (await s.execute(text("SELECT pdf_key, pdf_internal_key, pdf_attempts "
                                    "FROM sales_order WHERE id = CAST(:o AS uuid)"),
                               {"o": order["id"]})).one()
    finally:
        await s.close()
    assert row.pdf_key == f"orders/{order['id']}/old.pdf", "the customer copy is not rendered again"
    assert row.pdf_internal_key and row.pdf_internal_key.endswith("-internal.pdf")
    assert [f.name for f in tmp_path.rglob(f"orders/{order['id']}/*.pdf")] == \
        [pathlib.Path(row.pdf_internal_key).name]
    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho,
                         params={"copy": "internal"})
    assert r.status_code == 200, r.text


async def test_an_internal_copy_that_failed_five_times_is_pdf_failed_and_the_customer_copy_stands(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"]))
    await _run(sessions, "UPDATE sales_order SET pdf_state = 'ready', pdf_key = 'orders/x.pdf', "
                         "pdf_internal_key = NULL, pdf_internal_attempts = 5, "
                         "pdf_internal_error = 'font missing' WHERE id = CAST(:o AS uuid)",
               {"o": order["id"]})
    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho,
                         params={"copy": "internal"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "pdf_failed"
    assert r.json()["error"]["fields"]["pdf_error"] == "font missing"
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]
    assert (got["pdf_state"], got["pdf_internal_state"]) == ("ready", "failed")
    assert (await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)).status_code == 200


async def test_an_amend_clears_the_internal_copy(
        client: httpx.AsyncClient, shop: Shop, tmp_path: pathlib.Path, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"]))
    assert await _render(sessions, tmp_path, order["id"]) == "ready"
    r = await client.post(f"{V1}/orders/{order['id']}/amend",
                          json={"remark": "Customer cut the quantity",
                                "expected_status": "approved"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    s = sessions()
    try:
        row = (await s.execute(text("SELECT pdf_state, pdf_key, pdf_internal_key, "
                                    "pdf_internal_attempts FROM sales_order "
                                    "WHERE id = CAST(:o AS uuid)"), {"o": order["id"]})).one()
    finally:
        await s.close()
    assert (row.pdf_state, row.pdf_key, row.pdf_internal_key, row.pdf_internal_attempts) == \
        (None, None, None, 0)
