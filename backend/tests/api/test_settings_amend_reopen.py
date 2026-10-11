"""FS-036: company settings, amending an approved order, reopening a complaint.

The world is the order tests' shop. Settings are company-wide, so every test that
changes one restores it (the `restore` fixture)."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaint_remedies as remedies_t
from tests.api import test_complaints as complaints_t
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
remedies = remedies_t.remedies
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture
async def restore(sessions: Sessions) -> AsyncIterator[None]:
    """Every setting back to what it was, whatever the test changed."""
    c = sessions()
    before = {r.key: r for r in (await c.execute(text(
        "SELECT key::text AS key, value::text AS value, updated_by FROM app_setting"))).all()}
    await c.close()
    yield
    c = sessions()
    # updated_by too: a PATCH leaves the fixture's user there, and the shop's
    # teardown deletes that user (app_setting_updated_by_fkey)
    for key, row in before.items():
        await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb), updated_by = CAST(:u AS uuid) "
                             "WHERE key = :k AND (value <> CAST(:v AS jsonb) OR updated_by IS DISTINCT FROM CAST(:u AS uuid))"),
                        {"k": key, "v": row.value, "u": row.updated_by and str(row.updated_by)})
    await c.execute(text("DELETE FROM activity_event WHERE kind = 'setting.changed'"))
    await c.commit()
    await c.close()


async def _set(sessions: Sessions, key: str, value: Any) -> None:
    c = sessions()
    await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"),
                    {"k": key, "v": json.dumps(value)})
    await c.commit()
    await c.close()


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"].get("code"))


# ── settings ─────────────────────────────────────────────────────────────────

async def test_settings_are_listed_for_staff_and_changed_by_masters_edit_only(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/settings", headers=admin)
    assert r.status_code == 200, r.text
    got = {x["key"]: x for x in r.json()["data"]}
    assert {"order_amend_reapproval", "complaint_reopen_days", "complaint_reopen_roles",
            "complaint_reopen_clock", "complaint_reopen_max"} <= set(got)
    assert got["complaint_reopen_days"]["value"] == 30 and got["complaint_reopen_days"]["kind"] == "int"
    assert got["order_amend_reapproval"]["allowed"] == ["always", "value_rises"]

    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.patch(f"{V1}/settings", headers={**fo, **_key()}, json={"values": {"complaint_reopen_days": 10}})
    assert r.status_code == 403, r.text

    for values, field in (({"complaint_reopen_days": 0}, "complaint_reopen_days"),
                          ({"order_amend_reapproval": "sometimes"}, "order_amend_reapproval"),
                          ({"complaint_reopen_roles": ["no_such_role"]}, "complaint_reopen_roles"),
                          ({"nope": 1}, "nope")):
        r = await client.patch(f"{V1}/settings", headers={**admin, **_key()}, json={"values": values})
        assert r.status_code == 422 and field in r.json()["error"]["fields"], (values, r.text)

    r = await client.patch(f"{V1}/settings", headers={**admin, **_key()},
                           json={"values": {"complaint_reopen_days": 15, "order_amend_reapproval": "value_rises"}})
    assert r.status_code == 200, r.text
    got = {x["key"]: x["value"] for x in r.json()["data"]}
    assert (got["complaint_reopen_days"], got["order_amend_reapproval"]) == (15, "value_rises")
    # all or nothing: one bad value leaves the good one unchanged
    r = await client.patch(f"{V1}/settings", headers={**admin, **_key()},
                           json={"values": {"complaint_reopen_days": 20, "complaint_reopen_max": 99}})
    assert r.status_code == 422
    r = await client.get(f"{V1}/settings", headers=admin)
    assert {x["key"]: x["value"] for x in r.json()["data"]}["complaint_reopen_days"] == 15

    c = sessions()
    events = (await c.execute(text("SELECT payload FROM activity_event WHERE kind = 'setting.changed' "
                                   "AND payload->>'key' = 'complaint_reopen_days'"))).scalars().all()
    await c.close()
    assert [(e["from"], e["to"]) for e in events] == [(30, 15)]


async def test_a_direct_bad_value_is_refused_by_the_database(sessions: Sessions) -> None:
    c = sessions()
    try:
        with pytest.raises(DBAPIError) as err:
            await c.execute(text("UPDATE app_setting SET value = '\"payment_typo\"' WHERE key = 'order_amend_reapproval'"))
        assert getattr(err.value.orig, "sqlstate", None) == "SETVL"
    finally:
        await c.rollback()
        await c.close()



async def test_an_unknown_role_code_is_refused_on_change(sessions: Sessions) -> None:
    """041 skips the role check on its own insert (roles are seeded after migrating);
    every change after that is checked."""
    c = sessions()
    try:
        with pytest.raises(DBAPIError) as err:
            await c.execute(text("UPDATE app_setting SET value = '[\"support\", \"no_such_role\"]' "
                                 "WHERE key = 'complaint_reopen_roles'"))
        assert getattr(err.value.orig, "sqlstate", None) == "SETVL"
    finally:
        await c.rollback()
        await c.close()

# ── amend ────────────────────────────────────────────────────────────────────

async def _amend(client: httpx.AsyncClient, h: dict[str, str], oid: str, remark: str = "Farmer wants more") -> httpx.Response:
    return await client.post(f"{V1}/orders/{oid}/amend", headers={**h, **_key()}, json={"remark": remark})


def _roles(order: dict[str, Any]) -> list[str]:
    return [s["role"] for s in order["approval"]["steps"]]


async def test_an_approved_order_is_amended_and_approved_again_through_the_whole_chain(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    order = await conc._approved(client, shop)
    first_chain = _roles(order)
    fo = await endpoints._as(client, shop, "field_officer")
    r = await _amend(client, fo, order["id"])
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert (got["status"], got["order_no"], got["amend_count"]) == ("draft", order["order_no"], 1)
    assert got["amended_from_total"] == order["totals"]["total"] and got["pdf_state"] == "none"
    again = await endpoints._submit(client, fo, order["id"])
    assert _roles(again) == first_chain, "always: the whole chain again"
    c = sessions()
    kinds = (await c.execute(text("SELECT kind FROM activity_event WHERE entity_id = CAST(:o AS uuid) "
                                  "AND kind = 'order.amended'"), {"o": order["id"]})).scalars().all()
    await c.close()
    assert kinds == ["order.amended"]


async def test_value_rises_skips_the_managers_only_when_the_total_did_not_rise(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    await _set(sessions, "order_amend_reapproval", "value_rises")
    fo = await endpoints._as(client, shop, "field_officer")
    for qty, managers_skipped in (("5", True), ("40", False)):
        order = await conc._approved(client, shop)
        assert (await _amend(client, fo, order["id"])).status_code == 200
        r = await client.put(f"{V1}/orders/{order['id']}/lines", headers={**fo, **_key()},
                             json={"lines": [{"product_id": shop.product, "qty": qty, "discount_pct": "0"}]})
        assert r.status_code == 200, r.text
        roles = _roles(await endpoints._submit(client, fo, order["id"]))
        if managers_skipped:
            assert roles == ["account_manager", "dispatch_manager"], roles
        else:
            assert roles[:1] != ["account_manager"], roles


async def test_amend_is_refused_once_shipped_paid_or_a_replacement(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    shop = remedies
    fo = await endpoints._as(client, shop, "field_officer")
    shipped = await conc._approved(client, shop)
    dm = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{shipped['id']}/dispatches", headers={**dm, **_key()}, json={
        "dc_no": "DC-1", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": shipped["lines"][0]["id"], "qty": "1"}]})
    assert r.status_code in (200, 201), r.text
    r = await _amend(client, fo, shipped["id"])
    assert r.status_code == 409 and _code(r) == "order_dispatched", r.text

    paid = await conc._approved(client, shop)
    c = sessions()
    pay = str((await c.execute(text(
        "INSERT INTO payment (partner_id, mode, received_on, amount, entered_by) "
        "VALUES (NULL, 'cash', CURRENT_DATE, 10, CAST(:u AS uuid)) RETURNING id"), {"u": shop.ids["account_manager"]})).scalar_one())
    await c.execute(text("INSERT INTO payment_allocation (payment_id, sales_order_id, amount, created_by) "
                         "VALUES (CAST(:p AS uuid), CAST(:o AS uuid), 10, CAST(:u AS uuid))"),
                    {"p": pay, "o": paid["id"], "u": shop.ids["account_manager"]})
    await c.commit()
    await c.close()
    try:
        r = await _amend(client, fo, paid["id"])
        assert r.status_code == 409 and _code(r) == "order_has_payments", r.text
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM payment_allocation WHERE payment_id = CAST(:p AS uuid)"), {"p": pay})
        await c.execute(text("DELETE FROM payment WHERE id = CAST(:p AS uuid)"), {"p": pay})
        await c.commit()
        await c.close()

    _, replacement = await remedies_t._replacement(client, shop)
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await _amend(client, admin, replacement["id"])
    assert r.status_code == 422 and _code(r) == "order_type_fixed", r.text


async def test_an_amended_draft_needs_delete_to_cancel(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Review B-2: amending must not turn an approved-order cancel into an owner's."""
    order = await conc._approved(client, shop)
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await _amend(client, fo, order["id"])).status_code == 200
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", headers={**fo, **_key()}, json={"remark": "Not needed"})
    assert r.status_code == 403, r.text
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", headers={**admin, **_key()}, json={"remark": "Not needed"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled", r.text


async def test_order_amend_refuses_a_caller_who_cannot_see_the_order(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    order = await conc._approved(client, shop)
    s = sessions()
    try:
        await conc._as(s, shop.ids["dealer"])
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT order_amend(CAST(:o AS uuid), 'mine now', NULL)"), {"o": order["id"]})
        assert getattr(err.value.orig, "sqlstate", None) in ("ORDNF", "42501")
    finally:
        await s.rollback()
        await s.close()


async def test_a_dealer_cannot_amend_its_own_partners_order(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Review F-1: portal roles hold sales_orders.edit at partner_subtree, so the
    order must be one the dealer can see for the refusal to mean anything."""
    order = await conc._approved(client, shop)
    s = sessions()
    try:
        # the dealer's partner on a staff order, in this transaction only: setting it on
        # the draft reprices the lines at the dealer's tier and the submit refuses
        guards = ("trg_sales_order_refuse_edit", "trg_sales_order_parent_guard")
        for g in guards:
            await s.execute(text(f"ALTER TABLE sales_order DISABLE TRIGGER {g}"))
        await s.execute(text("UPDATE sales_order SET partner_id = CAST(:p AS uuid) WHERE id = CAST(:o AS uuid)"),
                        {"p": shop.partner, "o": order["id"]})
        for g in guards:
            await s.execute(text(f"ALTER TABLE sales_order ENABLE TRIGGER {g}"))
        await conc._as(s, shop.ids["dealer"])
        assert (await s.execute(text("SELECT order_visible(CAST(:o AS uuid))"), {"o": order["id"]})).scalar_one()
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT order_amend(CAST(:o AS uuid), 'mine now', NULL)"), {"o": order["id"]})
        assert getattr(err.value.orig, "sqlstate", None) == "42501"
    finally:
        await s.rollback()
        await s.close()


# ── reopen ───────────────────────────────────────────────────────────────────

async def _closed(client: httpx.AsyncClient, shop: Shop) -> dict[str, Any]:
    qc = await complaints_t._as(client, shop, "qc_manager")
    c = await remedies_t._qc_approved(client, shop)
    r = await remedies_t._remedy(client, qc, c["id"], kind="none", remark="Fixed on site")
    assert r.status_code == 200 and r.json()["data"]["status"] == "closed", r.text
    return dict(r.json()["data"])


async def _backdate(sessions: Sessions, cid: str) -> None:
    s = sessions()
    await s.execute(text("UPDATE complaint SET first_submitted_at = first_submitted_at - interval '30 days', "
                         "response_due_at = response_due_at - interval '30 days', "
                         "resolution_due_at = resolution_due_at - interval '30 days' "
                         "WHERE id = CAST(:c AS uuid)"), {"c": cid})
    await s.commit()
    await s.close()


async def _reopen(client: httpx.AsyncClient, h: dict[str, str], cid: str) -> httpx.Response:
    return await complaints_t._post(client, h, f"/{cid}/reopen", {"reason": "The same emitters failed again"})


async def test_the_raiser_reopens_a_closed_complaint_into_a_new_round(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    shop = remedies
    c = await _closed(client, shop)
    # review F-3: the first round a month back, so its targets are past and only a
    # restarted clock puts the new response target in the future
    await _backdate(sessions, c["id"])
    officer = await complaints_t._as(client, shop, "field_officer")
    detail = await remedies_t._get(client, officer, c["id"])
    assert detail["can"]["reopen"] is True
    assert dt.datetime.fromisoformat(detail["sla"]["response_due_at"]) < dt.datetime.now(dt.UTC)
    r = await _reopen(client, officer, c["id"])
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert (got["status"], got["reopen_count"], got["submit_count"], got["closed_at"]) == ("submitted", 1, 2, None)
    assert got["can"]["reopen"] is False
    # restart: the response target counts from now
    assert dt.datetime.fromisoformat(got["sla"]["response_due_at"]) > dt.datetime.now(dt.UTC)
    # the new round is checked afresh
    dm = await complaints_t._as(client, shop, "district_manager")
    r = await complaints_t._post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "Again genuine"})
    assert r.status_code == 200, r.text


async def test_a_reopen_nobody_can_check_is_refused(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    """Review F-4: as complaint_submit refuses, so does a reopen (CMPNC)."""
    shop = remedies
    c = await _closed(client, shop)
    s = sessions()
    try:
        await s.execute(text("UPDATE role_permission SET deleted_at = now() "
                             "WHERE module = 'complaints' AND action = 'approve' AND deleted_at IS NULL"))
        await conc._as(s, shop.ids["field_officer"])
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT complaint_reopen(CAST(:c AS uuid), 'Failed again')"), {"c": c["id"]})
        assert getattr(err.value.orig, "sqlstate", None) == "CMPNC"
    finally:
        await s.rollback()
        await s.close()


async def test_continue_keeps_the_original_targets(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions, restore: None) -> None:
    shop = remedies
    await _set(sessions, "complaint_reopen_clock", "continue")
    c = await _closed(client, shop)
    officer = await complaints_t._as(client, shop, "field_officer")
    before = (await remedies_t._get(client, officer, c["id"]))["sla"]["response_due_at"]
    r = await _reopen(client, officer, c["id"])
    assert r.status_code == 200 and r.json()["data"]["sla"]["response_due_at"] == before, r.text


async def test_a_rejection_is_reopened_by_the_allowed_roles_only(
        client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    officer = await complaints_t._as(client, shop, "field_officer")
    dm = await complaints_t._as(client, shop, "district_manager")
    qc = await complaints_t._as(client, shop, "qc_manager")
    c = await complaints_t._create(client, shop, officer)
    assert (await complaints_t._post(client, officer, f"/{c['id']}/submit")).status_code == 200
    assert (await complaints_t._post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "ok"})).status_code == 200
    r = await complaints_t._post(client, qc, f"/{c['id']}/qc", {"verdict": "rejected", "remark": "Misuse"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "qc_rejected", r.text
    assert (await _reopen(client, officer, c["id"])).status_code == 403
    r = await _reopen(client, qc, c["id"])
    assert r.status_code == 200 and r.json()["data"]["status"] == "submitted", r.text


async def test_the_window_and_the_cap_close_reopening(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions, restore: None) -> None:
    shop = remedies
    officer = await complaints_t._as(client, shop, "field_officer")
    old = await _closed(client, shop)
    s = sessions()
    await s.execute(text("UPDATE complaint SET closed_at = now() - interval '40 days' WHERE id = CAST(:c AS uuid)"),
                    {"c": old["id"]})
    await s.commit()
    await s.close()
    r = await _reopen(client, officer, old["id"])
    assert r.status_code == 422 and _code(r) == "reopen_window_closed", r.text

    await _set(sessions, "complaint_reopen_max", 1)
    c = await _closed(client, shop)
    assert (await _reopen(client, officer, c["id"])).status_code == 200
    s = sessions()
    await s.execute(text("UPDATE complaint SET status = 'closed', closed_at = now() WHERE id = CAST(:c AS uuid)"),
                    {"c": c["id"]})
    await s.commit()
    await s.close()
    r = await _reopen(client, officer, c["id"])
    assert r.status_code == 422 and _code(r) == "reopen_window_closed", r.text


async def test_complaint_reopen_refuses_a_caller_who_cannot_see_it(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    c = await _closed(client, remedies)
    s = sessions()
    try:
        await conc._as(s, remedies.ids["dispatch_manager"])
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT complaint_reopen(CAST(:c AS uuid), 'mine now', NULL)"), {"c": c["id"]})
        assert getattr(err.value.orig, "sqlstate", None) in ("CMPNF", "42501")
    finally:
        await s.rollback()
        await s.close()
