# ruff: noqa: E501  (request bodies inline)

"""FS-050 over the API: documents on leads, quotations, orders and dispatches."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_campaigns as camp
from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
JPEG, PDF = complaints_t.JPEG, complaints_t.PDF


@pytest_asyncio.fixture(autouse=True)
async def _clean(shop: Shop, sessions: Sessions, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[complaints_t._Counting]:
    storage = complaints_t._Counting()
    monkeypatch.setattr("api.routers.documents.get_storage", lambda *a, **k: storage)
    yield storage
    s = sessions()
    ids = list(shop.ids.values())
    await s.execute(text("DELETE FROM activity_event WHERE kind IN ('document.added', 'document.removed') "
                         "AND actor_id = ANY(CAST(:u AS uuid[]))"), {"u": ids})
    await s.execute(text("DELETE FROM record_document WHERE uploaded_by = ANY(CAST(:u AS uuid[]))"), {"u": ids})
    await s.execute(text("DELETE FROM notification_outbox WHERE payload->>'order_no' IN "
                         "(SELECT order_no::text FROM sales_order WHERE territory_id = CAST(:d AS uuid))"),
                    {"d": shop.district})
    await s.commit()
    await s.close()


async def _add(client: httpx.AsyncClient, h: dict[str, str], record_type: str, record_id: str, doc_type: str,
               data: bytes = JPEG, name: str | None = None) -> httpx.Response:
    form = {"record_type": record_type, "record_id": record_id, "doc_type": doc_type}
    if name is not None:
        form["name"] = name
    return await client.post(f"{V1}/documents", headers={**h, **_key()},
                             files={"file": ("slip.jpg", data, "image/jpeg")}, data=form)


async def test_documents_on_a_lead_its_order_and_dispatch_gather_on_the_lead(
        client: httpx.AsyncClient, shop: Shop, _clean: complaints_t._Counting) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    lead, order = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-DOC", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
                                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "1"}]})
    assert r.status_code == 201, r.text
    dispatch = r.json()["data"]

    r = await _add(client, ho, "lead", lead["id"], "land_record")
    assert r.status_code == 201, r.text
    again = await _add(client, ho, "lead", lead["id"], "land_record")
    assert again.status_code == 200 and again.json()["data"]["id"] == r.json()["data"]["id"], "same file, same type"
    assert (await _add(client, ho, "lead", lead["id"], "site_photo")).status_code == 201, "same file, another type"
    assert _clean.puts == 2
    r = await _add(client, ho, "lead", lead["id"], "other")
    assert r.status_code == 422 and "name" in r.json()["error"]["fields"], r.text
    assert (await _add(client, ho, "sales_order", order["id"], "payment_proof", PDF, name="June payment")).status_code == 201
    r = await _add(client, ho, "dispatch", dispatch["id"], "transport_receipt", PDF)
    assert r.status_code == 201, "the order's owner adds the LR (sales_orders.edit)"

    docs = (await client.get(f"{V1}/leads/{lead['id']}/documents", headers=ho)).json()["data"]
    got = sorted((d["record_type"], d["doc_type"], d["record_label"]) for d in docs)
    assert got == sorted([("lead", "land_record", lead["inquiry_no"]), ("lead", "site_photo", lead["inquiry_no"]),
                          ("sales_order", "payment_proof", order["order_no"]),
                          ("dispatch", "transport_receipt", dispatch["dispatch_no"])]), got
    slip = next(d for d in docs if d["doc_type"] == "payment_proof")
    assert slip["name"] == "June payment" and slip["doc_type_label"] == "Payment slip or receipt" and slip["preview"]

    # plan review B-1: an order's and a dispatch's documents reach the lead's timeline
    tl = (await client.get(f"{V1}/leads/{lead['id']}/timeline", headers=ho)).json()["data"]
    added = [e["payload"]["record_type"] for e in tl if e["kind"] == "document.added"]
    assert sorted(added) == ["dispatch", "lead", "lead", "sales_order"], added

    link = (await client.get(f"{V1}/documents/{slip['id']}/link", headers=ho)).json()["data"]
    assert link["url"].startswith("https://files.test/") and link["content_type"] == "application/pdf"
    assert (await client.delete(f"{V1}/documents/{slip['id']}", headers={**ho, **_key()})).status_code == 204
    left = (await client.get(f"{V1}/documents", headers=ho, params={"record_type": "sales_order", "record_id": order["id"]})).json()["data"]
    assert left == [], "deleted documents leave the list"


async def test_who_may_add_see_and_remove(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho, partner_id=shop.partner)
    lead_id = q["lead"]["id"]
    s = sessions()
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                    {"p": shop.partner, "l": lead_id})
    await s.commit()
    await s.close()
    staff_doc = (await _add(client, ho, "lead", lead_id, "land_record")).json()["data"]
    direct = await endpoints._create(client, ho, endpoints._direct(shop))
    assert (await _add(client, ho, "sales_order", direct["id"], "purchase_order", PDF)).status_code == 201

    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await _add(client, dealer, "quotation", q["id"], "signed_quotation")
        assert r.status_code == 403, "dealers view quotations only"
        r = await _add(client, dealer, "lead", lead_id, "site_photo", PDF)
        assert r.status_code == 201, r.text
        r = await client.delete(f"{V1}/documents/{staff_doc['id']}", headers={**dealer, **_key()})
        assert r.status_code == 403, "a dealer never removes a staff upload"
        r = await client.get(f"{V1}/documents", headers=dealer, params={"record_type": "sales_order", "record_id": direct["id"]})
        assert r.status_code == 404, "a direct sale is not the dealer's"
        r = await _add(client, dealer, "sales_order", direct["id"], "invoice")
        assert r.status_code == 404
    finally:
        await complaints_t._forget(sessions, mobile)


async def test_the_policy_hides_documents_and_editors_remove(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Code review 1: the read policy itself, not only the refusal, keeps a document
    from someone who cannot see its record; a staff editor removes another's upload;
    a merged lead takes no more."""
    ho = await endpoints._as(client, shop, "field_officer")
    lead = await camp._lead(client, ho, shop, village="Vadod")
    doc = (await _add(client, ho, "lead", lead["id"], "land_record")).json()["data"]
    s = sessions()
    try:
        # as someone with no claim on this shop's leads: the system principal's opposite,
        # a fresh uuid, reads nothing through the policy
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(uuid.uuid4())})
        await s.execute(text("SELECT set_config('role', 'app_role', true)"))
        seen = (await s.execute(text("SELECT count(*) FROM record_document WHERE id = CAST(:d AS uuid)"),
                                {"d": doc["id"]})).scalar_one()
        assert seen == 0, "the policy hides it"
    finally:
        await s.rollback()
        await s.close()
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.delete(f"{V1}/documents/{doc['id']}", headers={**dm, **_key()})
    assert r.status_code == 204, "a staff editor removes another's upload"

    other = await camp._lead(client, ho, shop, village="Vadod")
    r = await client.post(f"{V1}/leads/{other['id']}/merge", headers={**dm, **_key()},
                          json={"into_lead_id": lead["id"]})
    assert r.status_code == 200, r.text
    r = await _add(client, ho, "lead", other["id"], "site_photo")
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_closed", r.text

