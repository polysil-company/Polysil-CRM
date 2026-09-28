"""FS-015 over the API: a complaint from the form to the QC verdict, its files, what a
dealer sees, and the refusals. The world is the order tests' shop: one office, a
user per role, a dealer with a portal user. Other-office negatives are migration
019's tests."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import complaints as domain
from api.schemas import complaints as sch
from api.services import complaints as service
from api.storage import UnconfiguredStorage
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import PASSWORD, V1, _key, _login

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x01" * 64
PDF = b"%PDF-1.7\n" + b"\x02" * 64


async def _as(client: httpx.AsyncClient, shop: Shop, role: str) -> dict[str, str]:
    return await _login(client, shop.users[role], PASSWORD)


async def _type(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await client.get(f"{V1}/lookups/complaint-types", headers=h)
    assert r.status_code == 200, r.text
    return str(next(t["id"] for t in r.json()["data"] if t["code"] == "dripline"))


def _body(shop: Shop, type_id: str, **over: Any) -> dict[str, Any]:
    return {"complaint_type_id": type_id, "description": "Laterals cracking within two months",
            "contact_name": "Kiritbhai Shah", "contact_mobile": "98765 43210",
            "territory_id": shop.district, "dc_no": "DC-4471", "supply_date": "2026-07-14",
            "lines": [{"product_id": shop.product, "supplied_qty": "2000", "defective_qty": "340",
                       "failure_frequency": "every 3 to 4 m"}], **over}


async def _create(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], **over: Any) -> dict[str, Any]:
    r = await client.post(f"{V1}/complaints", json=_body(shop, await _type(client, h), **over),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def _post(client: httpx.AsyncClient, h: dict[str, str], path: str,
                body: dict[str, Any] | None = None) -> httpx.Response:
    return await client.post(f"{V1}/complaints{path}", json=body or {}, headers={**h, **_key()})


async def _upload(client: httpx.AsyncClient, h: dict[str, str], cid: str, data: bytes,
                  name: str = "lateral.jpg", declared: str = "image/jpeg",
                  kind: str = "photo") -> httpx.Response:
    return await client.post(f"{V1}/complaints/{cid}/attachments", headers={**h, **_key()},
                             files={"file": (name, data, declared)}, data={"kind": kind})


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


# ── the walk ─────────────────────────────────────────────────────────────────

async def test_the_whole_walk(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    qc = await _as(client, shop, "qc_manager")
    c = await _create(client, shop, officer)
    assert c["status"] == "draft" and c["complaint_no"] is None and c["sla"] is None
    assert c["contact_mobile"] == "+919876543210", "normalised"
    assert c["owner"]["id"] == shop.ids["field_officer"] and c["raised_by"]["id"] == shop.ids["field_officer"]
    assert c["can"]["submit"] and not c["can"]["check"] and c["can"]["upload"]
    assert c["lines"][0]["defective_qty"] == "340" and c["lines"][0]["uom"] is not None

    r = await _upload(client, officer, c["id"], JPEG)
    assert r.status_code == 201, r.text
    photo = r.json()["data"]
    assert photo["content_type"] == "image/jpeg" and photo["preview"]
    again = await _upload(client, officer, c["id"], JPEG, name="copy.jpg")
    assert again.status_code == 200 and again.json()["data"]["id"] == photo["id"], "the same file once"
    link = await client.get(f"{V1}/complaints/{c['id']}/attachments/{photo['id']}", headers=officer)
    assert link.status_code == 200 and link.json()["data"]["url"]

    r = await _post(client, officer, f"/{c['id']}/submit")
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "submitted" and c["complaint_no"].startswith("Poly/Comp./")
    assert c["sla"]["policy"] == "set" and c["sla"]["response_due_at"] and not c["sla"]["response_breached"]

    r = await _post(client, dm, f"/{c['id']}/check", {"decision": "return", "remark": "Add the challan photo",
                                                        "internal_note": "second time this month"})
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "draft" and c["check"]["decision"] == "return"
    assert c["check"]["internal_note"] == "second time this month", "staff see the note"
    await _upload(client, officer, c["id"], PDF, name="challan.pdf", declared="application/pdf", kind="challan")
    c = (await _post(client, officer, f"/{c['id']}/submit")).json()["data"]
    assert c["status"] == "submitted" and c["check"] is None and c["submit_count"] == 2

    r = await _post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "Genuine",
                                                        "severity": "high"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "under_qc" and r.json()["data"]["severity"] == "high"

    r = await _post(client, qc, f"/{c['id']}/qc", {"verdict": "approved", "remark": "Manufacturing defect",
                                                     "sample_received_on": "2026-07-20", "tested_on": "2026-07-22"})
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "qc_approved" and c["quality"]["verdict"] == "approved"
    assert c["sla"]["resolved_at"] is not None

    kinds = [e["kind"] for e in (await client.get(f"{V1}/complaints/{c['id']}/timeline", headers=officer)).json()["data"]]
    assert {"complaint.created", "complaint.submitted", "complaint.returned", "complaint.approved",
            "complaint.qc_approved", "complaint.attachment_added"} <= set(kinds)


async def test_the_list_and_the_queue(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    c = await _create(client, shop, officer)
    await _post(client, officer, f"/{c['id']}/submit")
    queue = (await client.get(f"{V1}/complaints", headers=dm, params={"awaiting": "me"})).json()["data"]
    assert c["id"] in {x["id"] for x in queue}
    mine = (await client.get(f"{V1}/complaints", headers=officer, params={"awaiting": "me"})).json()["data"]
    assert c["id"] not in {x["id"] for x in mine}, "nobody checks their own"
    found = (await client.get(f"{V1}/complaints", headers=officer, params={"q": "43210"})).json()["data"]
    assert c["id"] in {x["id"] for x in found}
    stats = (await client.get(f"{V1}/complaints/stats", headers=dm)).json()["data"]
    assert stats["by_status"]["submitted"] >= 1 and isinstance(stats["storage_available"], bool)


# ── refusals ─────────────────────────────────────────────────────────────────

async def test_submit_refuses_what_the_form_lacks(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h, dc_no=None, supply_date=None)
    r = await _post(client, h, f"/{c['id']}/submit")
    assert r.status_code == 422 and _code(r) == "missing_for_submit", r.text
    assert set(r.json()["error"]["fields"]) == {"dc_no", "supply_date"}
    c = await _create(client, shop, h, lines=[{"product_id": shop.product, "supplied_qty": "10",
                                                "defective_qty": "0"}])
    r = await _post(client, h, f"/{c['id']}/submit")
    assert r.status_code == 422 and _code(r) == "nothing_defective", r.text


@pytest.mark.parametrize(("over", "field"), [
    ({"contact_mobile": "+1 415 555 0100"}, "contact_mobile"),
    ({"supply_date": "2099-01-01"}, "supply_date"),
    ({"lines": [{"product_id": "P", "supplied_qty": "10", "defective_qty": "11"}]}, "lines[0].defective_qty"),
    ({"lines": [{"product_id": "P", "supplied_qty": "10", "defective_qty": "1"},
                {"product_id": "P", "supplied_qty": "5", "defective_qty": "1"}]}, "lines[1].product_id"),
])
async def test_the_form_is_checked_at_create(client: httpx.AsyncClient, shop: Shop,
                                              over: dict[str, Any], field: str) -> None:
    h = await _as(client, shop, "field_officer")
    if "lines" in over:
        over = {"lines": [{**ln, "product_id": shop.product} for ln in over["lines"]]}
    r = await client.post(f"{V1}/complaints", json=_body(shop, await _type(client, h), **over),
                          headers={**h, **_key()})
    assert r.status_code == 422 and field in r.json()["error"]["fields"], r.text


async def test_who_may_decide(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    qc = await _as(client, shop, "qc_manager")
    rm = await _as(client, shop, "regional_manager")
    c = await _create(client, shop, officer)
    await _post(client, officer, f"/{c['id']}/submit")
    assert (await _post(client, officer, f"/{c['id']}/check", {"decision": "approve", "remark": "x"})).status_code == 403
    assert (await _post(client, qc, f"/{c['id']}/check", {"decision": "approve", "remark": "x"})).status_code == 403, \
        "QC does not do the manager check"
    r = await _post(client, rm, f"/{c['id']}/check", {"decision": "approve", "remark": "ok"})
    assert r.status_code == 200, "a Regional Manager checks with approve alone (edge B-2)"
    assert (await _post(client, rm, f"/{c['id']}/qc", {"verdict": "approved", "remark": "x"})).status_code == 403, \
        "a line manager does not give the QC verdict"


async def test_qc_dates_must_be_possible(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    qc = await _as(client, shop, "qc_manager")
    c = await _create(client, shop, officer)
    await _post(client, officer, f"/{c['id']}/submit")
    await _post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "ok"})
    r = await _post(client, qc, f"/{c['id']}/qc", {"verdict": "rejected", "remark": "x",
                                                     "sample_received_on": "2026-07-01", "tested_on": "2026-06-30"})
    assert r.status_code == 422 and {"sample_received_on", "tested_on"} <= set(r.json()["error"]["fields"])


async def test_a_submitted_complaint_is_not_edited(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    await _post(client, h, f"/{c['id']}/submit")
    r = await client.patch(f"{V1}/complaints/{c['id']}", json={"description": "changed"}, headers={**h, **_key()})
    assert r.status_code == 409 and _code(r) == "complaint_not_draft"
    r = await client.put(f"{V1}/complaints/{c['id']}/lines", headers={**h, **_key()},
                         json={"lines": [{"product_id": shop.product, "supplied_qty": "1", "defective_qty": "1"}]})
    assert r.status_code == 409


async def test_cancel_by_the_raiser_and_its_reason(client: httpx.AsyncClient, shop: Shop,
                                                   sessions: Sessions) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    r = await _post(client, h, f"/{c['id']}/cancel", {"reason": "Raised by mistake"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled", r.text
    assert (await _post(client, h, f"/{c['id']}/submit")).status_code == 409


# ── files ────────────────────────────────────────────────────────────────────

async def test_a_file_is_judged_by_its_bytes_and_counted(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    r = await _upload(client, h, c["id"], b"<!DOCTYPE html><script>alert(1)</script>", name="x.jpg")
    assert r.status_code == 422 and _code(r) == "attachment_type", r.text
    for i in range(domain.MAX_ATTACHMENTS):
        r = await _upload(client, h, c["id"], JPEG + bytes([i]) * 3, name=f"p{i}.jpg")
        assert r.status_code == 201, (i, r.text)
    r = await _upload(client, h, c["id"], JPEG + b"\xee" * 3)
    assert r.status_code == 422 and _code(r) == "too_many_attachments", r.text


async def test_heic_is_kept_but_not_previewed(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x03" * 64
    r = await _upload(client, h, c["id"], heic, name="IMG_0001.HEIC", declared="application/octet-stream")
    assert r.status_code == 201 and r.json()["data"]["content_type"] == "image/heic"
    assert r.json()["data"]["preview"] is False


async def test_no_storage_is_a_503_and_nothing_is_kept(client: httpx.AsyncClient, shop: Shop,
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       sessions: Sessions) -> None:
    """EC-10: staging has no R2 yet. A 5xx is not stored, so a retry retries."""
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: UnconfiguredStorage())
    r = await _upload(client, h, c["id"], JPEG)
    assert r.status_code == 503 and _code(r) == "storage_unavailable", r.text
    s = sessions()
    try:
        n = (await s.execute(text("SELECT count(*) FROM complaint_attachment WHERE complaint_id = CAST(:c AS uuid)"),
                             {"c": c["id"]})).scalar_one()
    finally:
        await s.close()
    assert n == 0
    assert (await client.get(f"{V1}/complaints/{c['id']}", headers=h)).status_code == 200


async def test_after_submit_only_the_uploader_removes_a_file(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    c = await _create(client, shop, officer)
    photo = (await _upload(client, officer, c["id"], JPEG)).json()["data"]
    await _post(client, officer, f"/{c['id']}/submit")
    r = await client.delete(f"{V1}/complaints/{c['id']}/attachments/{photo['id']}", headers={**dm, **_key()})
    assert r.status_code == 403
    r = await client.delete(f"{V1}/complaints/{c['id']}/attachments/{photo['id']}", headers={**officer, **_key()})
    assert r.status_code == 204, r.text
    r = await client.get(f"{V1}/complaints/{c['id']}/attachments/{photo['id']}", headers=officer)
    assert r.status_code == 404


# ── what a dealer sees ───────────────────────────────────────────────────────

async def _dealer(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> tuple[dict[str, str], str]:
    s = sessions()
    mobile = str((await s.execute(text("SELECT mobile FROM app_user WHERE id = CAST(:u AS uuid)"),
                                  {"u": shop.ids["dealer"]})).scalar_one())
    await s.close()
    await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    c = sessions()
    code = (await c.execute(text(
        "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m ORDER BY created_at DESC LIMIT 1"),
        {"m": mobile})).scalar_one()
    await c.close()
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}, mobile


async def _forget(sessions: Sessions, mobile: str) -> None:
    e164 = mobile if mobile.startswith("+") else "+" + mobile
    c = sessions()
    for stmt in ("DELETE FROM notification_outbox WHERE recipient IN (:m, :raw)",
                 "DELETE FROM login_attempt WHERE identifier IN (:m, :raw)"):
        await c.execute(text(stmt), {"m": e164, "raw": mobile})
    await c.commit()
    await c.close()


async def test_a_dealer_raises_for_themselves_and_never_sees_who_decided(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    dm = await _as(client, shop, "district_manager")
    dealer, mobile = await _dealer(client, shop, sessions)
    try:
        type_id = (await client.get(f"{V1}/lookups/complaint-types", headers=dealer)).json()["data"][0]["id"]
        r = await client.post(f"{V1}/complaints", headers={**dealer, **_key()},
                              json=_body(shop, type_id, partner_id=str(uuid.uuid4())))
        assert r.status_code == 422, "a dealer does not raise for another"
        r = await client.post(f"{V1}/complaints", headers={**dealer, **_key()}, json=_body(shop, type_id))
        assert r.status_code == 201, r.text
        c = r.json()["data"]
        assert c["partner"]["id"] == shop.partner, "always their own"
        assert c["owner"] is None or c["owner"]["id"] == shop.ids["field_officer"], "the covering officer"
        assert (await _upload(client, dealer, c["id"], JPEG)).status_code == 201
        assert (await _post(client, dealer, f"/{c['id']}/submit")).status_code == 200
        r = await _post(client, dm, f"/{c['id']}/check", {"decision": "return", "remark": "Photo is blurred",
                                                            "internal_note": "dealer keeps doing this"})
        assert r.status_code == 200, r.text
        seen = (await client.get(f"{V1}/complaints/{c['id']}", headers=dealer)).json()["data"]
        assert seen["check"]["remark"] == "Photo is blurred"
        assert seen["check"]["by"] is None and seen["check"]["internal_note"] is None
        events = (await client.get(f"{V1}/complaints/{c['id']}/timeline", headers=dealer)).json()["data"]
        returned = next(e for e in events if e["kind"] == "complaint.returned")
        assert returned["actor"] is None
        assert (await _post(client, dealer, f"/{c['id']}/check", {"decision": "approve", "remark": "x"})).status_code == 403
    finally:
        await _forget(sessions, mobile)


# ── two managers at once ─────────────────────────────────────────────────────

def _check(shop: Shop, cid: str, role: str) -> conc.Work:
    async def work(s: AsyncSession) -> object:
        caller = Caller(shop.ids[role], shop.office, None, scopes={"complaints": "org_subtree"})
        return await service.check(s, caller, cid, sch.CheckIn(decision="approve", remark="ok"))
    return work


async def test_two_managers_at_once_leave_one_decision(client: httpx.AsyncClient, shop: Shop,
                                                       sessions: Sessions) -> None:
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    await _post(client, h, f"/{c['id']}/submit")
    got, waited = await conc._race(sessions, (shop.ids["district_manager"], _check(shop, c["id"], "district_manager")),
                                   (shop.ids["state_manager"], _check(shop, c["id"], "state_manager")))
    assert waited, "the second did not wait on the first"
    assert [conc._outcome(g) for g in got] == ["ok", "status_changed"], got


# ── the targets ──────────────────────────────────────────────────────────────

async def test_only_an_admin_sets_a_target(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    officer = await _as(client, shop, "field_officer")
    admin = await _as(client, shop, "admin_sales")
    body = {"severity": "low", "response_hours": 9, "resolution_hours": 45,
            "effective_from": (dt.date.today() + dt.timedelta(days=4000)).isoformat()}
    r = await client.post(f"{V1}/complaint-sla-policies", json=body, headers={**officer, **_key()})
    assert r.status_code == 403
    r = await client.post(f"{V1}/complaint-sla-policies", json=body, headers={**admin, **_key()})
    try:
        assert r.status_code == 201, r.text
        assert any(p["effective_from"] == body["effective_from"] for p in r.json()["data"])
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM complaint_sla_policy WHERE effective_from = :f"), {"f": dt.date.fromisoformat(body["effective_from"])})
        await s.execute(text("UPDATE complaint_sla_policy SET effective_to = NULL WHERE effective_to = :f"), {"f": dt.date.fromisoformat(body["effective_from"])})
        await s.commit()
        await s.close()


# ── code review (Fable, on the build) ────────────────────────────────────────

class _Counting:
    """A storage that counts writes, so a refusal is shown to cost no object."""

    name = "counting"

    def __init__(self) -> None:
        self.puts = 0

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.puts += 1

    def presign_get(self, key: str, *, filename: str, disposition: str = "inline") -> tuple[str, dt.datetime]:
        return f"https://files.test/{key}?{disposition}", dt.datetime.now(tz=dt.UTC)


async def test_the_lead_timeline_never_names_the_decider_to_a_dealer(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """F-1, executed by the reviewer: `actor` was hidden, `actor_name` rode in the payload."""
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    lead = (await client.post(f"{V1}/leads", headers={**officer, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    s = sessions()
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                    {"p": shop.partner, "l": lead["id"]})
    await s.commit()
    await s.close()
    c = await _create(client, shop, officer, lead_id=lead["id"], partner_id=shop.partner)
    await _post(client, officer, f"/{c['id']}/submit")
    await _post(client, dm, f"/{c['id']}/check", {"decision": "return", "remark": "Photo please"})
    dealer, mobile = await _dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/leads/{lead['id']}/timeline", headers=dealer)
        assert r.status_code == 200, r.text
        returned = next(e for e in r.json()["data"] if e["kind"] == "complaint.returned")
        assert returned["actor"] is None and "actor_name" not in returned["payload"], returned
        staff = (await client.get(f"{V1}/leads/{lead['id']}/timeline", headers=officer)).json()["data"]
        mine = next(e for e in staff if e["kind"] == "complaint.returned")
        assert mine["actor"]["id"] == shop.ids["district_manager"], "staff still see who"
    finally:
        await _forget(sessions, mobile)


async def test_a_refused_upload_writes_nothing(client: httpx.AsyncClient, shop: Shop,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """F-2: the status and the permission come before the write."""
    officer = await _as(client, shop, "field_officer")
    rm = await _as(client, shop, "regional_manager")
    storage = _Counting()
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: storage)
    c = await _create(client, shop, officer)
    r = await _upload(client, rm, c["id"], JPEG)
    assert r.status_code == 403, "view and approve without edit add no files"
    await _post(client, officer, f"/{c['id']}/cancel", {"reason": "Mistake"})
    r = await _upload(client, officer, c["id"], JPEG)
    assert r.status_code == 409 and _code(r) == "complaint_closed_for_upload", r.text
    assert storage.puts == 0
    other = await _create(client, shop, officer)
    assert (await _upload(client, officer, other["id"], JPEG)).status_code == 201
    assert storage.puts == 1


async def test_a_new_dealer_cannot_keep_another_dealers_order(client: httpx.AsyncClient,
                                                              shop: Shop) -> None:
    """F-3: a partner change re-checks the order already on the complaint."""
    officer = await _as(client, shop, "field_officer")
    order = await endpoints._create(client, officer, endpoints._direct(shop, partner_id=shop.partner))
    c = await _create(client, shop, officer, partner_id=shop.partner, sales_order_id=order["id"])
    assert c["sales_order"]["id"] == order["id"]
    r = await client.patch(f"{V1}/complaints/{c['id']}", json={"partner_id": None}, headers={**officer, **_key()})
    assert r.status_code == 422 and "sales_order_id" in r.json()["error"]["fields"], r.text
    r = await client.post(f"{V1}/complaints", json=_body(shop, c["complaint_type"]["id"], sales_order_id=order["id"]),
                          headers={**officer, **_key()})
    assert r.status_code == 422, "an order of a dealer, on a complaint with none"


async def test_two_uploads_at_once_keep_the_cap(client: httpx.AsyncClient, shop: Shop,
                                                sessions: Sessions) -> None:
    """F-4: FOR SHARE let both count nine; FOR UPDATE makes the second wait."""
    officer = await _as(client, shop, "field_officer")
    c = await _create(client, shop, officer)
    s = sessions()
    for i in range(domain.MAX_ATTACHMENTS - 1):
        await s.execute(text(
            "INSERT INTO complaint_attachment (complaint_id, kind, storage_key, filename, content_type, "
            "size_bytes, sha256, uploaded_by) VALUES (CAST(:c AS uuid), 'photo', :k, 'p.jpg', 'image/jpeg', 10, "
            ":h, CAST(:u AS uuid))"),
            {"c": c["id"], "k": f"complaints/{c['id']}/seed{i}", "h": f"{i:064x}", "u": shop.ids["field_officer"]})
    await s.commit()
    await s.close()
    caller = Caller(shop.ids["field_officer"], shop.office, None, scopes={"complaints": "own"})

    def upload(data: bytes) -> conc.Work:
        async def work(session: AsyncSession) -> object:
            return await service.add_attachment(session, caller, c["id"], kind="photo", filename="x.jpg",
                                                data=data, storage=_Counting())
        return work
    me = shop.ids["field_officer"]
    got, waited = await conc._race(sessions, (me, upload(JPEG + b"a")), (me, upload(JPEG + b"b")))
    assert waited, "the second upload did not wait on the first"
    assert [conc._outcome(g) for g in got] == ["ok", "too_many_attachments"], got


def test_download_names_keep_their_type_and_never_become_a_quotation() -> None:
    """F-5, executed by the reviewer: a Gujarati name became `jpg`, `...` became
    `quotation.pdf`."""
    assert service._download_name("ફોટો.jpg", "image/jpeg") == "attachment.jpg"
    assert service._download_name("...", "application/pdf") == "attachment.pdf"
    assert service._download_name("lateral photo (1).jpg", "image/jpeg") == "lateral-photo-1.jpg"
    assert service._download_name("IMG_0001.HEIC", "image/heic") == "IMG_0001.heic"
    assert service._safe_filename("...", "jpg") == "attachment.jpg"


async def test_a_file_just_over_ten_megabytes_is_a_413(client: httpx.AsyncClient, shop: Shop) -> None:
    """F-7: under the framing allowance the middleware lets it through; the route
    answers the same 413."""
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    big = JPEG + b"\x00" * (domain.MAX_UPLOAD_BYTES + 10 * 1024 - len(JPEG))
    r = await _upload(client, h, c["id"], big)
    assert r.status_code == 413 and _code(r) == "attachment_too_large", r.text


async def test_the_owner_of_a_dealers_complaint_is_the_covering_officer(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """F-8: the earlier assertion passed whatever lead_auto_owner returned."""
    dealer, mobile = await _dealer(client, shop, sessions)
    try:
        type_id = (await client.get(f"{V1}/lookups/complaint-types", headers=dealer)).json()["data"][0]["id"]
        c = (await client.post(f"{V1}/complaints", headers={**dealer, **_key()},
                               json=_body(shop, type_id))).json()["data"]
        assert c["owner"] is not None and c["owner"]["id"] == shop.ids["field_officer"]
        assert c["owner_org_unit"]["id"] == shop.office
    finally:
        await _forget(sessions, mobile)


async def test_a_return_takes_no_severity_or_owner(client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    c = await _create(client, shop, officer)
    await _post(client, officer, f"/{c['id']}/submit")
    r = await _post(client, dm, f"/{c['id']}/check", {"decision": "return", "remark": "x", "severity": "high"})
    assert r.status_code == 422, r.text


async def test_delete_is_for_a_never_submitted_draft_and_needs_delete(
        client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    admin = await _as(client, shop, "admin_sales")
    draft = await _create(client, shop, officer)
    assert (await client.delete(f"{V1}/complaints/{draft['id']}", headers={**officer, **_key()})).status_code == 403
    assert (await client.delete(f"{V1}/complaints/{draft['id']}", headers={**admin, **_key()})).status_code == 204
    assert (await client.get(f"{V1}/complaints/{draft['id']}", headers=admin)).status_code == 404
    sent = await _create(client, shop, officer)
    await _post(client, officer, f"/{sent['id']}/submit")
    r = await client.delete(f"{V1}/complaints/{sent['id']}", headers={**admin, **_key()})
    assert r.status_code == 409, "a submitted complaint is cancelled, not deleted"


async def test_after_a_503_the_same_key_really_retries(client: httpx.AsyncClient, shop: Shop,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-10: the 5xx is not stored as the key's answer."""
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    key = _key()
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: UnconfiguredStorage())
    files = {"file": ("a.jpg", JPEG, "image/jpeg")}
    r = await client.post(f"{V1}/complaints/{c['id']}/attachments", headers={**h, **key}, files=files)
    assert r.status_code == 503
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: _Counting())
    r = await client.post(f"{V1}/complaints/{c['id']}/attachments", headers={**h, **key}, files=files)
    assert r.status_code == 201, r.text


async def test_a_dealer_cannot_see_or_touch_a_complaint_without_them(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    officer = await _as(client, shop, "field_officer")
    c = await _create(client, shop, officer)               # no dealer on it
    dealer, mobile = await _dealer(client, shop, sessions)
    try:
        assert (await client.get(f"{V1}/complaints/{c['id']}", headers=dealer)).status_code == 404
        assert (await _upload(client, dealer, c["id"], JPEG)).status_code == 404
        assert (await _post(client, dealer, f"/{c['id']}/submit")).status_code in (403, 404)
    finally:
        await _forget(sessions, mobile)



# ── cross-vendor review (astra) ──────────────────────────────────────────────

async def test_a_name_search_without_digits_works(client: httpx.AsyncClient, shop: Shop) -> None:
    """Astra P2, reproduced: no digits bound a NUL character and every name search was a 500."""
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    r = await client.get(f"{V1}/complaints", headers=h, params={"q": "Kirit"})
    assert r.status_code == 200, r.text
    assert c["id"] in {x["id"] for x in r.json()["data"]}


async def test_the_cancel_reason_can_be_read_back(client: httpx.AsyncClient, shop: Shop) -> None:
    """Astra P2: the reason was stored and read by nothing (the B-8 shape once more)."""
    h = await _as(client, shop, "field_officer")
    c = await _create(client, shop, h)
    r = await _post(client, h, f"/{c['id']}/cancel", {"reason": "Raised on the wrong farmer"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]["cancellation"]
    assert got["reason"] == "Raised on the wrong farmer" and got["by"]["id"] == shop.ids["field_officer"]
    fresh = (await client.get(f"{V1}/complaints/{c['id']}", headers=h)).json()["data"]
    assert fresh["cancellation"]["reason"] == "Raised on the wrong farmer"
