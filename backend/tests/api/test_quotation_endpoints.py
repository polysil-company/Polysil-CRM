"""/quotations and /public/q, end to end over ASGI (FS-005 4, 10).

Every test signs in as a staff user whose role holds the quotation permissions,
builds a qualified lead in a state of its own, and quotes the catalogue product
FS-010's tests price. The worker's render is exercised in-process with the HTML
renderer and a temporary local store, because WeasyPrint does not import on the
Windows box; the PDF text-layer test lives with the worker tests and skips here.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.errors import ApiError
from api.services import quotations as service
from api.services.clock import today_ist
from api.storage import LocalStorage
from tests.api.conftest import PASSWORD, V1, Catalogue, Staff, _auth, _key
from worker.jobs.quotations import render_one

pytestmark = pytest.mark.db

AS_OF = "2020-06-15"


@dataclass
class QEnv:
    district_id: str
    state_id: str
    state_code: str


@pytest_asyncio.fixture
async def quoter(sessions: Callable[[], AsyncSession], staff: Staff) -> AsyncIterator[Staff]:
    """The staff user with the quotation permissions the lead permissions imply
    (RBAC 6.1: every role that creates quotations edits leads)."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'quotations', 'view', 'global'), (:r, 'quotations', 'create', 'global'), "
        "(:r, 'quotations', 'edit', 'global'), (:r, 'quotations', 'delete', 'global'), "
        "(:r, 'pricing', 'view', 'global') ON CONFLICT DO NOTHING"),
        {"r": staff.role_id})
    await s.commit()
    yield staff


@pytest_asyncio.fixture
async def officer(sessions: Callable[[], AsyncSession], quoter: Staff) -> AsyncIterator[Staff]:
    """A second person who quotes and may not delete: quotations view, create and
    edit at global and no `delete`, so RLS hides soft-deleted rows from them
    (code review F-1). Tests list it before `qenv`, so it outlives the rows it
    creates; the teardown removes them anyway in case the order changes."""
    tag = uuid.uuid4().hex[:10]
    email = f"officer_{tag}@polysil.in"
    s = sessions()
    role = str((await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Quoting Officer', 1) RETURNING id"),
        {"c": f"api_qo_{tag}"})).scalar_one())
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'global'), (:r, 'leads', 'create', 'global'), "
        "(:r, 'leads', 'edit', 'global'), "
        "(:r, 'quotations', 'view', 'global'), (:r, 'quotations', 'create', 'global'), "
        "(:r, 'quotations', 'edit', 'global'), (:r, 'pricing', 'view', 'global')"), {"r": role})
    user = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, :p, 'Kiran Desai', :r, :o) RETURNING id"),
        {"e": email, "p": PasswordHasher().hash(PASSWORD), "r": role,
         "o": quoter.org_unit_id})).scalar_one())
    await s.commit()
    try:
        yield Staff(user, email, PASSWORD, quoter.org_unit_id, role)
    finally:
        c = sessions()
        for stmt in (
            "DELETE FROM activity_event WHERE actor_id = CAST(:u AS uuid) "
            "OR entity_id = CAST(:u AS uuid) OR entity_id IN "
            "(SELECT id FROM quotation WHERE created_by = CAST(:u AS uuid))",
            "DELETE FROM quotation WHERE created_by = CAST(:u AS uuid)",
            "DELETE FROM idempotency_record WHERE user_id = CAST(:u AS uuid)",
            "DELETE FROM session WHERE user_id = CAST(:u AS uuid)",
            "DELETE FROM login_attempt WHERE identifier = CAST(:e AS citext)",
            "DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
            "DELETE FROM role_permission WHERE role_id = CAST(:r AS uuid)",
            "DELETE FROM role WHERE id = CAST(:r AS uuid)",
        ):
            await c.execute(text(stmt), {"u": user, "e": email, "r": role})
        await c.commit()


@pytest_asyncio.fixture
async def qenv(sessions: Callable[[], AsyncSession], quoter: Staff,
               catalogue: Catalogue) -> AsyncIterator[QEnv]:
    """A coded state over a district, and a teardown that removes the quotations
    before the leads they hang off and before the catalogue rows they price from
    (so it depends on the catalogue: pytest tears down in reverse)."""
    tag = uuid.uuid4().hex[:8]
    code = "Q" + tag[:3].upper()
    s = sessions()
    state = str((await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"quote_state_{tag}", "c": code})).scalar_one())
    district = str((await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"quote_district_{tag}", "p": state})).scalar_one())
    await s.commit()
    try:
        yield QEnv(district, state, code)
    finally:
        c = sessions()
        leads = "(SELECT id FROM lead WHERE territory_id = :d)"
        for stmt in (
            # the immutability trigger refuses the un-linking of sent versions, and
            # the two self-FKs make the delete order circular; this session is the
            # owner, so it may switch the trigger off for the cleanup
            "ALTER TABLE quotation DISABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM activity_event WHERE lead_id IN {leads}",
            "DELETE FROM notification_outbox WHERE template_key = 'quotation_share' "
            "AND recipient IN (SELECT party_mobile FROM quotation WHERE territory_id = :d)",
            "UPDATE quotation SET supersedes_id = NULL, superseded_by_id = NULL "
            "WHERE territory_id = :d",
            "DELETE FROM quotation WHERE territory_id = :d",
            "ALTER TABLE quotation ENABLE TRIGGER trg_quotation_refuse_sent_edit",
            "DELETE FROM idempotency_record WHERE route LIKE '%/quotations%' "
            "AND created_at > now() - interval '1 hour'",
            f"DELETE FROM lead_duplicate_link WHERE lead_a_id IN {leads} OR lead_b_id IN {leads}",
            "DELETE FROM notification_outbox WHERE recipient IN "
            "(SELECT mobile FROM lead WHERE territory_id = :d)",
            "DELETE FROM lead WHERE territory_id = :d",
            "DELETE FROM quotation_counter WHERE state_code = :c",
            "DELETE FROM inquiry_counter WHERE state_code = :c",
            "DELETE FROM territory WHERE id = :d",
            "DELETE FROM territory WHERE id = :s",
        ):
            await c.execute(text(stmt), {"d": district, "s": state, "c": code})
        await c.commit()


async def _qualified_lead(client: httpx.AsyncClient, h: dict[str, str], env: QEnv,
                          **over: object) -> dict:
    body: dict[str, object] = {
        "farmer_name": "Rameshbhai Patel", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": env.district_id, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod",
    }
    body.update(over)
    r = await client.post(f"{V1}/leads", json=body, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    lead = r.json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return r.json()["data"]


def _line(cat: Catalogue, **over: object) -> dict[str, object]:
    line: dict[str, object] = {"product_id": cat.product_id, "qty": "18", "discount_pct": "10",
                               "discount2_pct": "5"}
    line.update(over)
    return line


def _create_body(lead_id: str, cat: Catalogue, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "lead_id": lead_id, "sales_type": "commercial",
        "place_of_supply_territory_id": cat.gujarat_district_id,
        "seller_gstin_id": cat.gstin_id, "price_effective_date": AS_OF,
        "partner_id": None, "lines": [_line(cat)],
    }
    body.update(over)
    return body


async def _draft(client: httpx.AsyncClient, h: dict[str, str], env: QEnv, cat: Catalogue,
                 **over: object) -> dict:
    lead = await _qualified_lead(client, h, env)
    r = await client.post(f"{V1}/quotations", json=_create_body(lead["id"], cat, **over),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _send(client: httpx.AsyncClient, h: dict[str, str], qid: str,
                channel: str = "none") -> dict:
    r = await client.post(f"{V1}/quotations/{qid}/send", json={"channel": channel},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _local_settings(tmp: pathlib.Path):
    return get_settings().model_copy(update={"pdf_renderer": "html",
                                             "public_web_url": "http://localhost:3000"})


async def _render(tmp: pathlib.Path) -> str | None:
    settings = _local_settings(tmp)
    storage = LocalStorage(root=tmp, secret=b"test", public_base="")
    return await render_one(settings, storage)


# ── create ───────────────────────────────────────────────────────────────────

async def test_a_draft_is_priced_on_save_and_has_no_number(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    lead = await _qualified_lead(client, h, qenv)
    r = await client.post(f"{V1}/quotations", json=_create_body(lead["id"], catalogue),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["status"] == "draft" and q["quote_no"] is None and q["version"] == 1
    assert q["lead"] == {"id": lead["id"], "inquiry_no": lead["inquiry_no"], "stage": "qualified"}
    assert q["party"]["name"] == "Rameshbhai Patel" and q["party"]["mobile"] == lead["mobile"]
    assert q["party"]["address"] == "Vadod, " + lead["territory"]["name"]
    assert q["owner"]["id"] == quoter.id, "the lead's owner"
    assert q["intra_state"] is True and q["place_of_supply"]["state"] == "GJ"
    line = q["lines"][0]
    assert (line["gross"], line["discount1_amt"], line["after_discount1"],
            line["discount2_amt"], line["taxable"]) == ("1857.42", "185.74", "1671.68",
                                                        "83.58", "1588.10")
    assert line["cgst"] == line["sgst"] == "39.70" and line["total"] == "1667.50"
    assert q["totals"]["total"] == "1667.50" and q["is_provisional"] is True
    assert q["share_url"] is None and q["pdf_state"] is None and q["valid_until"] is None
    assert any(w.startswith("provisional_pricing:") for w in q["warnings"])


async def test_a_new_lead_cannot_be_quoted(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "New Lead", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": qenv.district_id, "inquiry_type": "commercial", "mis_system": "drip"})
    lead = r.json()["data"]
    r = await client.post(f"{V1}/quotations", json=_create_body(lead["id"], catalogue),
                          headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "lead_not_qualified"


async def test_an_unbuilt_sales_type_names_its_question(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    lead = await _qualified_lead(client, h, qenv)
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()},
                          json=_create_body(lead["id"], catalogue, sales_type="export"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "sales_type_unsupported"
    assert "14.5" in r.json()["error"]["message"]


async def test_a_stale_preview_id_is_refused_with_the_new_figures(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """Rule 4: the ids the preview showed are compared after re-resolution."""
    h = await _auth(client, quoter)
    lead = await _qualified_lead(client, h, qenv)
    stale = _line(catalogue, price_list_item_id=str(uuid.uuid4()))
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()},
                          json=_create_body(lead["id"], catalogue, lines=[stale]))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rate_changed"
    assert "lines[0].rate" in r.json()["error"]["fields"]


# ── draft edits ──────────────────────────────────────────────────────────────

async def test_patching_a_draft_reprices_and_uppercases_the_gstin(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    r = await client.patch(f"{V1}/quotations/{q['id']}", headers={**h, **_key()}, json={
        "party": {"name": "Patel Agro Pvt Ltd", "mobile": q["party"]["mobile"],
                  "gstin": "24aaacp1234a1z5"},
        "terms": "Ex-works.", "expected_status": "draft"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert got["party"]["gstin"] == "24AAACP1234A1Z5" and got["terms"] == "Ex-works."
    assert got["lines"][0]["total"] == "1667.50", "re-priced to the same figures"

    stale = await client.patch(f"{V1}/quotations/{q['id']}", headers={**h, **_key()},
                               json={"terms": "x", "expected_status": "sent"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "status_changed"


async def test_lines_are_replaced_wholesale_and_may_be_empty_on_a_draft(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    r = await client.put(f"{V1}/quotations/{q['id']}/lines", headers={**h, **_key()},
                         json={"lines": [_line(catalogue, qty="2", discount_pct="0"),
                                         _line(catalogue, qty="1")]})
    assert r.status_code == 200, r.text
    lines = r.json()["data"]["lines"]
    assert [ln["line_no"] for ln in lines] == [1, 2] and lines[0]["gross"] == "206.38"
    empty = await client.put(f"{V1}/quotations/{q['id']}/lines", headers={**h, **_key()},
                             json={"lines": []})
    assert empty.status_code == 200 and empty.json()["data"]["totals"]["total"] == "0.00"
    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_lines"


# ── send ─────────────────────────────────────────────────────────────────────

async def test_send_numbers_freezes_and_moves_the_lead(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    sent = await _send(client, h, q["id"])
    assert sent["status"] == "sent" and sent["quote_no"] == f"QT/{qenv.state_code}/{_fy()}/00001"
    assert sent["valid_until"] == (today_ist() + dt.timedelta(days=45)).isoformat()
    assert sent["share_url"].startswith("http://localhost:3000/q/")
    assert sent["pdf_state"] == "pending"
    assert sent["seller_gstin"]["gstin"] and sent["lead"]["stage"] == "quoted"

    again = await client.get(f"{V1}/quotations/{q['id']}", headers=h)
    assert again.json()["data"]["share_url"] == sent["share_url"], "on every read"
    twice = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                              headers={**h, **_key()})
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "quotation_not_draft"

    lead = await client.get(f"{V1}/leads/{q['lead']['id']}", headers=h)
    assert lead.json()["data"]["stage"] == "quoted"
    timeline = await client.get(f"{V1}/leads/{q['lead']['id']}/timeline", headers=h)
    kinds = [e["kind"] for e in timeline.json()["data"]]
    assert "quotation.sent" in kinds and "lead.stage_changed" in kinds
    ev = next(e for e in timeline.json()["data"] if e["kind"] == "lead.stage_changed"
              and e["payload"].get("via") == "quotation")
    assert ev["payload"]["from"] == "qualified" and ev["payload"]["to"] == "quoted"
    # the seller block is a snapshot now
    row = (await sessions().execute(text(
        "SELECT seller_legal_name, share_token FROM quotation WHERE id = :id"),
        {"id": q["id"]})).one()
    assert row.seller_legal_name == "Polysil Test" and len(row.share_token) == 43


async def test_a_sent_document_refuses_every_edit(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    for call in (
        client.patch(f"{V1}/quotations/{q['id']}", headers={**h, **_key()}, json={"terms": "x"}),
        client.put(f"{V1}/quotations/{q['id']}/lines", headers={**h, **_key()},
                   json={"lines": []}),
        client.request("DELETE", f"{V1}/quotations/{q['id']}", headers={**h, **_key()},
                       json={}),
    ):
        r = await call
        assert r.status_code == 409 and r.json()["error"]["code"] == "quotation_not_draft"


def _fy() -> str:
    today = today_ist()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


# ── the answer ───────────────────────────────────────────────────────────────

async def test_acceptance_wins_the_lead_and_is_refused_past_validity(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted", "remark": "yes", "expected_status": "sent"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert got["status"] == "accepted" and got["accepted_at"] and got["lead"]["stage"] == "won"
    assert got["decided_by"]["id"] == quoter.id and got["decision_remark"] == "yes"

    other = await _draft(client, h, qenv, catalogue)
    await _send(client, h, other["id"])
    s = sessions()
    # the trigger refuses this on a sent row, which is the point of the trigger;
    # the test session is the owner and switches it off to age the document
    await s.execute(text("ALTER TABLE quotation DISABLE TRIGGER trg_quotation_refuse_sent_edit"))
    await s.execute(text("UPDATE quotation SET valid_until = :d WHERE id = :id"),
                    {"d": today_ist() - dt.timedelta(days=1), "id": other["id"]})
    await s.execute(text("ALTER TABLE quotation ENABLE TRIGGER trg_quotation_refuse_sent_edit"))
    await s.commit()
    r = await client.post(f"{V1}/quotations/{other['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "quotation_expired"


async def test_a_second_acceptance_on_a_won_lead_moves_nothing(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """GAP-117: a head unit and a field unit quoted separately."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                      json={"to": "accepted"})
    # a second unit on the now-won lead
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()},
                          json=_create_body(q["lead"]["id"], catalogue))
    assert r.status_code == 201, r.text
    second = await _send(client, h, r.json()["data"]["id"])
    assert second["lead"]["stage"] == "won"
    r = await client.post(f"{V1}/quotations/{second['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted"})
    assert r.status_code == 200 and r.json()["data"]["lead"]["stage"] == "won"


async def test_negotiation_moves_the_lead_and_rejection_does_not(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "negotiation"})
    assert r.status_code == 200 and r.json()["data"]["lead"]["stage"] == "negotiation"
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "rejected", "remark": "too dear"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    assert r.json()["data"]["lead"]["stage"] == "negotiation", "rejection moves nothing"
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_transition"


# ── revise ───────────────────────────────────────────────────────────────────

async def test_a_revision_keeps_the_number_and_sending_it_supersedes(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    sent = await _send(client, h, q["id"])
    r = await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**h, **_key()},
                          json={"price_effective_date": AS_OF})
    assert r.status_code == 201, r.text
    v2 = r.json()["data"]
    assert v2["version"] == 2 and v2["quote_no"] == sent["quote_no"] and v2["status"] == "draft"
    assert v2["supersedes"] == {"id": q["id"], "version": 1}
    assert v2["lines"][0]["total"] == "1667.50"

    again = await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**h, **_key()},
                              json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "revision_exists"

    v2_sent = await _send(client, h, v2["id"])
    assert v2_sent["status"] == "sent" and v2_sent["quote_no"] == sent["quote_no"]
    v1 = (await client.get(f"{V1}/quotations/{q['id']}", headers=h)).json()["data"]
    assert v1["superseded_by"] == {"id": v2["id"], "version": 2} and v1["status"] == "sent"
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "quotation_superseded"
    r = await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**h, **_key()}, json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "quotation_superseded"

    versions = (await client.get(f"{V1}/quotations/{v2['id']}/versions", headers=h)).json()
    assert [v["version"] for v in versions["data"]] == [1, 2]
    listed = (await client.get(f"{V1}/quotations?lead_id={q['lead']['id']}", headers=h)).json()
    assert [x["version"] for x in listed["data"]] == [2], "current_only hides the superseded"
    every = (await client.get(f"{V1}/quotations?lead_id={q['lead']['id']}&current_only=false",
                              headers=h)).json()
    assert sorted(x["version"] for x in every["data"]) == [1, 2]


async def test_revise_then_delete_then_revise_numbers_above_the_deleted_draft(
        client: httpx.AsyncClient, quoter: Staff, officer: Staff, qenv: QEnv,
        catalogue: Catalogue) -> None:
    """Round 2 B-6: UNIQUE (quote_no, version) counts soft-deleted rows. Code
    review F-1: the second revision is the officer's, who holds no
    `quotations.delete` and so cannot see the deleted draft under RLS. A count
    under their policies said 2, and the insert hit `uq_quotation_no_version`
    as a 500; `quotation_next_version()` counts as the owner."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    v2 = (await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**h, **_key()},
                            json={"price_effective_date": AS_OF})).json()["data"]
    r = await client.request("DELETE", f"{V1}/quotations/{v2['id']}", headers={**h, **_key()},
                             json={"expected_status": "draft"})
    assert r.status_code == 204, r.text
    ho = await _auth(client, officer)
    r = await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**ho, **_key()},
                          json={"price_effective_date": AS_OF})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["version"] == 3


async def test_an_accepted_predecessor_blocks_the_send_of_its_revision(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """Edge case 7: revise, then accept v1, then try to send v2."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    v2 = (await client.post(f"{V1}/quotations/{q['id']}/revise", headers={**h, **_key()},
                            json={"price_effective_date": AS_OF})).json()["data"]
    r = await client.post(f"{V1}/quotations/{q['id']}/transition", headers={**h, **_key()},
                          json={"to": "accepted"})
    assert r.status_code == 200
    r = await client.post(f"{V1}/quotations/{v2['id']}/send", headers={**h, **_key()},
                          json={"channel": "none"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "predecessor_accepted"


# ── the list and the timeline ────────────────────────────────────────────────

async def test_the_list_counts_on_request_and_the_timeline_carries_no_money(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    page = (await client.get(f"{V1}/quotations?lead_id={q['lead']['id']}&include_total=true",
                             headers=h)).json()
    assert page["meta"]["total"] == 1 and page["data"][0]["quote_no"]
    # code review F-6: a global caller holding delete has a predicate of `true`,
    # which names no column, and a count with no FROM was one row whatever existed
    await _draft(client, h, qenv, catalogue)
    everything = (await client.get(f"{V1}/quotations?include_total=true", headers=h)).json()
    assert everything["meta"]["total"] >= 2, everything["meta"]
    if len(everything["data"]) < 25:
        assert everything["meta"]["total"] == len(everything["data"]), everything["meta"]
    found = (await client.get(f"{V1}/quotations?q={q['party']['mobile'][-6:]}", headers=h)).json()
    assert any(x["id"] == q["id"] for x in found["data"])
    tl = (await client.get(f"{V1}/quotations/{q['id']}/timeline", headers=h)).json()
    kinds = [e["kind"] for e in tl["data"]]
    assert kinds[:2] == ["quotation.sent", "quotation.created"]
    for e in tl["data"]:
        assert not any(k in e["payload"] for k in ("total", "gross", "taxable"))


# ── the PDF and the public link ──────────────────────────────────────────────

async def test_the_pdf_is_pending_until_the_worker_renders_it(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        tmp_path: pathlib.Path, sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    r = await client.get(f"{V1}/quotations/{q['id']}/pdf", headers=h)
    assert r.status_code == 404, "no PDF on a draft"
    sent = await _send(client, h, q["id"], channel="whatsapp")
    r = await client.get(f"{V1}/quotations/{q['id']}/pdf", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "pdf_pending"

    assert await _render(tmp_path) == "ready"
    got = (await client.get(f"{V1}/quotations/{q['id']}", headers=h)).json()["data"]
    assert got["pdf_state"] == "ready"
    link = (await client.get(f"{V1}/quotations/{q['id']}/pdf", headers=h)).json()["data"]
    assert link["filename"] == sent["quote_no"].replace("/", "-") + "-v1.pdf"
    assert "/public/files/" in link["url"]
    files = list(tmp_path.rglob("v1-*.pdf"))  # one object per render lease
    assert len(files) == 1 and b"INDICATIVE PRICING" in files[0].read_bytes().upper()
    assert b"Rameshbhai Patel" in files[0].read_bytes()
    # the message went out only now, with the whole link
    row = (await sessions().execute(text(
        "SELECT payload FROM notification_outbox WHERE template_key = 'quotation_share' "
        "AND recipient = :m ORDER BY created_at DESC LIMIT 1"),
        {"m": q["party"]["mobile"]})).one()
    payload = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)
    assert payload["link"] == sent["share_url"] and payload["quote_no"] == sent["quote_no"]


async def test_the_public_link_shows_no_party_data_and_records_the_view_on_the_pdf(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        tmp_path: pathlib.Path) -> None:
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    sent = await _send(client, h, q["id"])
    token = sent["share_url"].rsplit("/", 1)[1]

    pub = await client.get(f"/public/q/{token}")
    assert pub.status_code == 200, pub.text
    body = pub.json()["data"]
    assert body["quote_no"] == sent["quote_no"] and body["totals"]["total"] == "1667.50"
    assert body["expired"] is False and body["superseded"] is False and body["pdf_ready"] is False
    assert "Rameshbhai" not in pub.text and q["party"]["mobile"] not in pub.text
    assert set(body) == {"quote_no", "version", "status", "sales_type", "seller", "sent_at",
                         "valid_until", "expired", "superseded", "totals", "line_count",
                         "pdf_ready", "pdf_url"}
    # the JSON is not a view
    before = (await client.get(f"{V1}/quotations/{q['id']}", headers=h)).json()["data"]
    assert before["viewed_at"] is None

    pending = await client.get(f"/public/q/{token}/pdf", follow_redirects=False)
    assert pending.status_code == 409 and pending.json()["error"]["code"] == "pdf_pending"
    assert await _render(tmp_path) == "ready"
    opened = await client.get(f"/public/q/{token}/pdf", follow_redirects=False)
    assert opened.status_code == 302 and "/public/files/" in opened.headers["location"]
    got = (await client.get(f"{V1}/quotations/{q['id']}", headers=h)).json()["data"]
    assert got["status"] == "viewed" and got["viewed_at"] and got["open_count"] == 1
    await client.get(f"/public/q/{token}/pdf", follow_redirects=False)
    got = (await client.get(f"{V1}/quotations/{q['id']}", headers=h)).json()["data"]
    assert got["open_count"] == 2 and got["status"] == "viewed", "later opens only count"

    assert (await client.get("/public/q/" + "x" * 43)).status_code == 404


class _StorageDown:
    """R2 unconfigured, as on staging before the bucket exists."""

    def presign_get(self, key: str, *, filename: str) -> tuple[str, dt.datetime]:
        raise RuntimeError("R2 is not configured (r2_endpoint, r2_bucket, r2_access_key_id, "
                           "r2_secret_access_key); local disk is not allowed")


async def test_a_storage_failure_never_names_configuration_to_the_public_link(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        tmp_path: pathlib.Path, sessions: Callable[[], AsyncSession]) -> None:
    """API review L4: the farmer's link got the storage error verbatim."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    sent = await _send(client, h, q["id"])
    assert await _render(tmp_path) == "ready"
    token = sent["share_url"].rsplit("/", 1)[1]
    s = sessions()
    try:
        with pytest.raises(ApiError) as caught:
            await service.public_open(s, token, None, _StorageDown())  # type: ignore[arg-type]
    finally:
        await s.rollback()
        await s.close()
    assert caught.value.code == "storage_unavailable"
    assert "r2" not in caught.value.message.lower() and "config" not in caught.value.message.lower()


async def test_the_quotation_list_takes_several_statuses(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """API review: "open quotations" in one call."""
    h = await _auth(client, quoter)
    draft = await _draft(client, h, qenv, catalogue)
    sent = await _send(client, h, (await _draft(client, h, qenv, catalogue))["id"])

    async def ids(status: str) -> set[str]:
        r = await client.get(f"{V1}/quotations", headers=h, params={"status": status, "limit": 100})
        assert r.status_code == 200, r.text
        return {x["id"] for x in r.json()["data"]} & {draft["id"], sent["id"]}

    assert await ids("draft,sent") == {draft["id"], sent["id"]}
    assert await ids("sent,viewed,negotiation") == {sent["id"]}
    assert await ids("accepted") == set()


# ── delete ───────────────────────────────────────────────────────────────────

async def test_a_draft_can_be_deleted_and_then_is_not_there(
        client: httpx.AsyncClient, quoter: Staff, officer: Staff, qenv: QEnv,
        catalogue: Catalogue, sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-8: the row is marked, not removed, and a reader without
    `quotations.delete` finds it on neither the detail nor the list."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    r = await client.request("DELETE", f"{V1}/quotations/{q['id']}", headers={**h, **_key()},
                             json={})
    assert r.status_code == 204
    s = sessions()
    marked = (await s.execute(text("SELECT deleted_at FROM quotation WHERE id = CAST(:q AS uuid)"),
                              {"q": q["id"]})).scalar_one()
    await s.rollback()
    assert marked is not None, "soft-deleted, and still there for the audit trail"
    ho = await _auth(client, officer)
    assert (await client.get(f"{V1}/quotations/{q['id']}", headers=ho)).status_code == 404
    listed = (await client.get(f"{V1}/quotations?lead_id={q['lead']['id']}", headers=ho)).json()
    assert all(x["id"] != q["id"] for x in listed["data"])


# ── the closed lead, the discontinued product, the owner filter ──────────────

async def _lose(client: httpx.AsyncClient, h: dict[str, str], lead_id: str,
                sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    reason = str((await s.execute(text(
        "SELECT id FROM won_lost_reason WHERE kind = 'lost' AND is_active LIMIT 1"))).scalar_one())
    await s.rollback()
    r = await client.post(f"{V1}/leads/{lead_id}/transition",
                          json={"to_stage": "lost", "lost_reason_id": reason},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text


async def test_a_closed_lead_refuses_the_send_the_answer_and_the_revision(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 12 and round 4 B-3 (code review F-3): `lead_lock_for_quotation(.., true)`
    is the first call of send, transition and revise, and a lost lead refuses all
    three with `lead_not_open`; a draft on a lost lead stays editable and
    deletable, because it is locked with `require_open = false`."""
    h = await _auth(client, quoter)
    sent = await _send(client, h, (await _draft(client, h, qenv, catalogue))["id"])
    await _lose(client, h, sent["lead"]["id"], sessions)
    for path, body in (("transition", {"to": "accepted"}),
                       ("revise", {"price_effective_date": AS_OF})):
        r = await client.post(f"{V1}/quotations/{sent['id']}/{path}", json=body,
                              headers={**h, **_key()})
        assert r.status_code == 422, (path, r.text)
        assert r.json()["error"]["code"] == "lead_not_open", (path, r.text)
    draft = await _draft(client, h, qenv, catalogue)
    await _lose(client, h, draft["lead"]["id"], sessions)
    r = await client.post(f"{V1}/quotations/{draft['id']}/send", json={"channel": "none"},
                          headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "lead_not_open", r.text
    r = await client.patch(f"{V1}/quotations/{draft['id']}", json={"terms": "Still editable"},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    r = await client.request("DELETE", f"{V1}/quotations/{draft['id']}", json={},
                             headers={**h, **_key()})
    assert r.status_code == 204, r.text


async def test_a_discontinued_product_warns_on_a_revision_and_is_refused_on_a_new_line(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """Edge case 8, rule 5 (code review F-7): the pipeline's warning reaches the
    response of the write that produced it, at revise and again at send; a new
    line on the product is refused."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    s = sessions()
    await s.execute(text("UPDATE product SET is_active = false WHERE id = CAST(:p AS uuid)"),
                    {"p": catalogue.product_id})
    await s.commit()
    try:
        r = await client.post(f"{V1}/quotations/{q['id']}/revise",
                              json={"price_effective_date": AS_OF}, headers={**h, **_key()})
        assert r.status_code == 201, r.text
        v2 = r.json()["data"]
        assert any(w.startswith("discontinued_products:") for w in v2["warnings"]), v2["warnings"]
        sent = await _send(client, h, v2["id"])
        assert any(w.startswith("discontinued_products:") for w in sent["warnings"]), sent
        lead = await _qualified_lead(client, h, qenv)
        r = await client.post(f"{V1}/quotations", json=_create_body(lead["id"], catalogue),
                              headers={**h, **_key()})
        assert r.status_code == 422 and r.json()["error"]["code"] == "product_inactive", r.text
    finally:
        s = sessions()
        await s.execute(text("UPDATE product SET is_active = true WHERE id = CAST(:p AS uuid)"),
                        {"p": catalogue.product_id})
        await s.commit()


async def test_a_malformed_owner_filter_is_refused_not_a_500(
        client: httpx.AsyncClient, quoter: Staff) -> None:
    """Code review F-11: the column is a uuid, so the parameter's shape is checked
    before it reaches the bind."""
    h = await _auth(client, quoter)
    assert (await client.get(f"{V1}/quotations?owner=kiran", headers=h)).status_code == 422
    assert (await client.get(f"{V1}/quotations?owner=me", headers=h)).status_code == 200


async def test_a_seller_state_change_is_refused_at_send_though_no_id_moved(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """Cross-vendor A-1: the registration's state moves after the save, so the
    line's price row and tax-rate row are unchanged and the split is not. The
    send refuses with the new figures instead of freezing CGST and SGST."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    assert q["lines"][0]["cgst"] != "0.00", "saved intra-state"
    s = sessions()
    home = (await s.execute(text(
        "SELECT state_territory_id FROM seller_gstin WHERE id = CAST(:g AS uuid)"),
        {"g": catalogue.gstin_id})).scalar_one()
    await s.execute(text("UPDATE seller_gstin SET state_territory_id = CAST(:st AS uuid) "
                         "WHERE id = CAST(:g AS uuid)"),
                    {"st": qenv.state_id, "g": catalogue.gstin_id})
    await s.commit()
    try:
        r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                              headers={**h, **_key()})
        assert r.status_code == 409 and r.json()["error"]["code"] == "rate_changed", r.text
        assert "igst" in r.json()["error"]["fields"]["lines[0].tax"], r.json()["error"]
    finally:
        # the test's state is torn down before the catalogue's registration
        await s.execute(text("UPDATE seller_gstin SET state_territory_id = :home "
                             "WHERE id = CAST(:g AS uuid)"),
                        {"home": home, "g": catalogue.gstin_id})
        await s.commit()


async def test_a_price_date_too_far_ahead_names_the_quotations_own_field(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue) -> None:
    """PR #10 review: the refusal named `as_of`, which the quotation forms do not
    have, so the screen could not attach it to the input."""
    h = await _auth(client, quoter)
    lead = await _qualified_lead(client, h, qenv)
    far = (today_ist() + dt.timedelta(days=800)).isoformat()
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()},
                          json=_create_body(lead["id"], catalogue, price_effective_date=far))
    assert r.status_code == 422, r.text
    fields = r.json()["error"]["fields"]
    assert "price_effective_date" in fields and "as_of" not in fields, fields
