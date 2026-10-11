# ruff: noqa: E501  (embedded SQL and request bodies)

"""Fixes from the staging walk of 10 Oct.

- F-1 (ISS-107): what a dealer reads of a lead it can see. Staff notes, the lost
  reason and duplicate handling are internal (GAP-284); the dealer's own notes stay.
- F-16: the history names the other lead of a merge, a flag or a dismissal, once.
- F-11: an approval step whose own role has nobody says so (`stalled`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _post(client: httpx.AsyncClient, h: dict[str, str], path: str, body: dict) -> httpx.Response:
    return await client.post(f"{V1}/leads{path}", json=body, headers={**h, **_key()})


async def _new_lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], mobile: str) -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": mobile, "territory_id": shop.district,
        "inquiry_type": "commercial", "mis_system": "drip", "village": "Vadod"})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_a_dealer_reads_the_stage_but_not_the_staff_words(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    officer = await complaints_t._as(client, shop, "field_officer")
    mobile = "97" + f"{uuid.uuid4().int % 10**8:08d}"
    await _new_lead(client, shop, officer, mobile)
    lead = await _new_lead(client, shop, officer, mobile)   # the second is flagged a possible duplicate
    s = sessions()
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                    {"p": shop.partner, "l": lead["id"]})
    reason = str((await s.execute(text(
        "SELECT id FROM won_lost_reason WHERE kind = 'lost' AND is_active AND deleted_at IS NULL LIMIT 1"))).scalar_one())
    await s.commit()
    await s.close()
    lid = lead["id"]
    assert (await _post(client, officer, f"/{lid}/notes", {"note": "staff only: push the 5%"})).status_code in (200, 201)
    r = await _post(client, officer, f"/{lid}/transition",
                    {"to_stage": "lost", "lost_reason_id": reason, "lost_note": "staff lost words"})
    assert r.status_code == 200, r.text
    assert (await _post(client, officer, f"/{lid}/reopen", {"note": "staff reopen words"})).status_code == 200

    dealer, dealer_mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await _post(client, dealer, f"/{lid}/notes", {"note": "dealer visited the farm"})
        assert r.status_code in (200, 201), r.text

        staff = (await client.get(f"{V1}/leads/{lid}/timeline", headers=officer)).json()["data"]
        kinds = {e["kind"] for e in staff}
        assert {"lead.note_added", "lead.duplicate_flagged", "lead.stage_changed", "lead.reopened"} <= kinds, kinds

        r = await client.get(f"{V1}/leads/{lid}/timeline", headers=dealer)
        assert r.status_code == 200, r.text
        seen = r.json()["data"]
        text_seen = str(seen)
        for words in ("push the 5%", "staff lost words", "staff reopen words", reason):
            assert words not in text_seen, (words, seen)
        assert not {e["kind"] for e in seen} & {"lead.duplicate_flagged", "lead.duplicate_dismissed", "lead.merged"}
        notes = [e["payload"].get("note") for e in seen if e["kind"] == "lead.note_added"]
        assert notes == ["dealer visited the farm"], notes
        lost = next(e for e in seen if e["kind"] == "lead.stage_changed" and e["payload"].get("to") == "lost")
        assert lost["payload"]["from"] and "lost_reason_id" not in lost["payload"], lost

        detail = (await client.get(f"{V1}/leads/{lid}", headers=dealer)).json()["data"]
        assert detail["score"] is None and detail["duplicates"] == [], detail
        # code review F-1: the lost reason and note are staff words on the lead too.
        # Lost again so the row holds them (the reopen cleared them).
        r = await _post(client, officer, f"/{lid}/transition",
                        {"to_stage": "lost", "lost_reason_id": reason, "lost_note": "staff lost words"})
        assert r.status_code == 200, r.text
        detail = (await client.get(f"{V1}/leads/{lid}", headers=dealer)).json()["data"]
        assert detail["lost_reason"] is None and detail["lost_note"] is None, detail
        listed_lost = (await client.get(f"{V1}/leads", headers=dealer)).json()["data"]
        assert "staff lost words" not in str(listed_lost)
        assert (await client.get(f"{V1}/leads/{lid}", headers=officer)).json()["data"]["lost_note"] == "staff lost words"
        staff_detail = (await client.get(f"{V1}/leads/{lid}", headers=officer)).json()["data"]
        assert staff_detail["duplicates"], "staff still see the pair"
        listed = (await client.get(f"{V1}/leads", headers=dealer)).json()["data"]
        assert listed and all(x["score"] is None for x in listed)

        queue = await client.get(f"{V1}/leads/duplicates", headers=dealer)
        assert queue.status_code == 200 and queue.json()["data"] == [], queue.text
        link = staff_detail["duplicates"][0]["link_id"]
        r = await client.post(f"{V1}/leads/duplicates/{link}/dismiss", headers={**dealer, **_key()})
        assert r.status_code == 403, r.text
    finally:
        await complaints_t._forget(sessions, dealer_mobile)


# ── walk F-16: the history names the leads, once ─────────────────────────────

async def test_the_history_names_the_other_lead_once_and_an_edit_is_no_new_flag(
        client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await complaints_t._as(client, shop, "district_manager")
    mobile = "97" + f"{uuid.uuid4().int % 10**8:08d}"
    a = await _new_lead(client, shop, dm, mobile)
    b = await _new_lead(client, shop, dm, mobile)

    async def _events(lid: str, kind: str) -> list[dict]:
        r = await client.get(f"{V1}/leads/{lid}/timeline", headers=dm)
        assert r.status_code == 200, r.text
        return [e for e in r.json()["data"] if e["kind"] == kind]

    flagged = await _events(b["id"], "lead.duplicate_flagged")
    assert len(flagged) == 1 and flagged[0]["payload"]["matches"][0]["inquiry_no"] == a["inquiry_no"], flagged
    r = await client.patch(f"{V1}/leads/{b['id']}", json={"village": "Vadod East"}, headers={**dm, **_key()})
    assert r.status_code == 200, r.text
    assert len(await _events(b["id"], "lead.duplicate_flagged")) == 1, "re-finding a known pair is no news"

    link = (await client.get(f"{V1}/leads/{b['id']}", headers=dm)).json()["data"]["duplicates"][0]["link_id"]
    r = await client.post(f"{V1}/leads/duplicates/{link}/dismiss", headers={**dm, **_key()})
    assert r.status_code == 200, r.text
    dismissed = (await _events(b["id"], "lead.duplicate_dismissed"))[0]["payload"]
    assert (dismissed["other_lead_id"], dismissed["other_inquiry_no"]) == (a["id"], a["inquiry_no"]), dismissed

    c = await _new_lead(client, shop, dm, mobile)
    r = await _post(client, dm, f"/{c['id']}/merge", {"into_lead_id": a["id"]})
    assert r.status_code == 200, r.text
    merged = await _events(a["id"], "lead.merged")
    assert len(merged) == 1, merged
    assert (merged[0]["payload"]["loser_inquiry_no"], merged[0]["payload"]["survivor_inquiry_no"]) \
        == (c["inquiry_no"], a["inquiry_no"]), merged


# ── walk F-11: the step waiting now, when its own role cannot decide it ──────

async def test_a_step_whose_role_has_nobody_says_stalled(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Nobody of the step's own role covers the order: here the district manager is
    switched off, as on staging the only one had raised the order herself."""
    ho = await endpoints._as(client, shop, "field_officer")
    dm_id = shop.ids["district_manager"]

    async def _dm_active(on: bool) -> None:
        s = sessions()
        await s.execute(text("UPDATE app_user SET is_active = :on WHERE id = CAST(:u AS uuid)"),
                        {"on": on, "u": dm_id})
        await s.commit()
        await s.close()

    try:
        order = await endpoints._submit(client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"])
        steps = order["approval"]["steps"]
        assert steps[0]["role"] == "district_manager" and not any(x["stalled"] for x in steps), steps
        await _dm_active(False)
        again = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]["approval"]["steps"]
        assert [x["stalled"] for x in again] == [True] + [False] * (len(again) - 1), again
        s = sessions()
        try:
            await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": shop.ids["dealer"]})
            await s.execute(text("SELECT set_config('role', 'app_role', true)"))
            seen = (await s.execute(text("SELECT approval_waiting_stalled(CAST(:r AS uuid))"),
                                    {"r": order["approval"]["request_id"]})).scalar_one()
            assert seen is False, "a caller who cannot see the order learns nothing"
        finally:
            await s.rollback()
            await s.close()
    finally:
        await _dm_active(True)
        s = sessions()
        await s.execute(text("DELETE FROM notification_outbox WHERE payload->>'order_no' IN "
                             "(SELECT order_no::text FROM sales_order WHERE territory_id = CAST(:d AS uuid))"),
                        {"d": shop.district})
        await s.commit()
        await s.close()
