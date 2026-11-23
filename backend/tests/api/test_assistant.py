# ruff: noqa: E501  (request bodies and assertions)

"""FS-045 over the API: actions by permission, records by scope."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_customers import _cleanup, _lead, _mobile, _move

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _ask(client: httpx.AsyncClient, h: dict[str, str], q: str | None, **params: object) -> dict:
    r = await client.get(f"{V1}/assistant", params={**({"q": q} if q is not None else {}), **params}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_actions_follow_the_role(client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    ha = await endpoints._as(client, shop, "admin_sales")
    officer = {x["key"] for x in (await client.get(f"{V1}/assistant/actions", headers=ho)).json()["data"]}
    admin = {x["key"] for x in (await client.get(f"{V1}/assistant/actions", headers=ha)).json()["data"]}
    assert "lead.create" in officer and "masters.holidays" not in officer
    assert "masters.holidays" in admin
    assert [x["key"] for x in (await _ask(client, ha, "holiday"))["actions"]] == ["masters.holidays"]
    assert (await _ask(client, ho, "holiday"))["actions"] == []
    assert (await _ask(client, ho, None))["actions"][0]["key"] == "lead.create"


async def test_records_only_in_scope_never_deleted_or_merged(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    hdm = await endpoints._as(client, shop, "district_manager")
    m1, m2 = _mobile(), _mobile()
    try:
        mine = await _move(client, ho, (await _lead(client, ho, shop, m1, name="Zaverbhai Assist"))["id"],
                           "contacted", "qualified")
        theirs = await _lead(client, hdm, shop, m2, name="Zaverbhai Hidden")
        # by name: the officer sees their own lead and its customer, not the manager's
        recs = (await _ask(client, ho, "zaverbhai"))["records"]
        assert {(r["kind"], r["id"]) for r in recs} == {("lead", mine["id"]), ("customer", mine["customer_id"])}, recs
        # the manager sees both leads
        ids = {r["id"] for r in (await _ask(client, hdm, "zaverbhai"))["records"] if r["kind"] == "lead"}
        assert {mine["id"], theirs["id"]} <= ids
        # by mobile, any spelling, and by number, any case, prefix or serial
        for q in (f"+91 {m1[:5]} {m1[5:]}", m1, mine["inquiry_no"].lower(), mine["inquiry_no"][:-2],
                  mine["inquiry_no"].rsplit("/", 1)[1]):
            got = {r["id"] for r in (await _ask(client, ho, q))["records"] if r["kind"] == "lead"}
            assert mine["id"] in got, q
        # too short for records; control characters refused; wildcards literal
        assert (await _ask(client, ho, "za"))["records"] == []
        r = await client.get(f"{V1}/assistant", params={"q": "za\x01"}, headers=ho)
        assert r.status_code == 422, r.text
        assert (await _ask(client, ho, "%%%"))["records"] == []
        assert (await client.get(f"{V1}/assistant", params={"limit": 0}, headers=ho)).status_code == 422

        # deleted and merged leads never appear
        s = sessions()
        await s.execute(text("UPDATE lead SET deleted_at = now() WHERE id = CAST(:i AS uuid)"), {"i": theirs["id"]})
        await s.commit()
        await s.close()
        ha = await endpoints._as(client, shop, "admin_sales")
        ids = {r["id"] for r in (await _ask(client, ha, "zaverbhai"))["records"] if r["kind"] == "lead"}
        assert theirs["id"] not in ids
    finally:
        await _cleanup(sessions, [m1, m2])


async def test_a_dealer_sees_its_leads_and_no_staff_actions(client: httpx.AsyncClient, shop: Shop,
                                                           sessions: Sessions) -> None:
    from tests.api import test_complaints as cmp
    hd, dealer_mobile = await cmp._dealer(client, shop, sessions)
    ho = await endpoints._as(client, shop, "field_officer")
    m1, m2 = _mobile(), _mobile()
    try:
        own = await _lead(client, hd, shop, m1, name="Dealerbhai Search")
        other = await _lead(client, ho, shop, m2, name="Dealerbhai Search")
        ids = {r["id"] for r in (await _ask(client, hd, "dealerbhai"))["records"]}
        assert own["id"] in ids and other["id"] not in ids
        keys = {x["key"] for x in (await client.get(f"{V1}/assistant/actions", headers=hd)).json()["data"]}
        assert "lead.duplicates" not in keys and "lead.qr" not in keys
    finally:
        await cmp._forget(sessions, dealer_mobile)
        await _cleanup(sessions, [m1, m2])


async def test_documents_by_number_merged_leads_and_literal_wildcards(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    hdm = await endpoints._as(client, shop, "district_manager")
    q = await endpoints._accepted_quotation(client, shop, hdm)
    m1, m2 = _mobile(), _mobile()
    try:
        # the manager finds the quotation by prefix and by serial; the officer, outside
        # its scope (the manager owns it), does not
        serial = q["quote_no"].rsplit("/", 1)[1]
        for text_ in (q["quote_no"].lower(), q["quote_no"][:-3], serial):
            got = [r for r in (await _ask(client, hdm, text_))["records"] if r["kind"] == "quotation"]
            assert q["id"] in {r["id"] for r in got}, text_
        assert not [r for r in (await _ask(client, ho, q["quote_no"]))["records"] if r["kind"] == "quotation"]

        # a merged lead is never offered
        loser = await _lead(client, ho, shop, m1, name="Mergebhai Loser")
        survivor = await _lead(client, ho, shop, m2, name="Mergebhai Survivor")
        r = await client.post(f"{V1}/leads/{loser['id']}/merge", json={"into_lead_id": survivor["id"]},
                              headers={**hdm, **_key()})
        assert r.status_code == 200, r.text
        ids = {r["id"] for r in (await _ask(client, hdm, "mergebhai"))["records"] if r["kind"] == "lead"}
        assert survivor["id"] in ids and loser["id"] not in ids

        # % and _ match themselves, not everything
        odd = await _lead(client, ho, shop, _mobile(), name="Per%cent_bhai")
        ids = {r["id"] for r in (await _ask(client, ho, "per%cent_"))["records"]}
        assert ids == {odd["id"]}, ids
        assert not (await _ask(client, ho, "pe__ent"))["records"]
    finally:
        await _cleanup(sessions, [m1, m2])
