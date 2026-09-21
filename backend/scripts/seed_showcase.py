#!/usr/bin/env python3
"""Seed the showcase dataset through the API (FS-006 section 5).

    python scripts/seed_showcase.py

Run `seed_demo.py` first: it creates the roles, the permission matrix and the
administrator this script signs in as. Idempotent by code, email, mobile and lead
mobile, so a second run changes no counts.

Four passes, and which connection does what:

  0  owner   removes what earlier killed test runs left behind (older than an hour)
  1  API     territories and offices, as the seeded administrator
  2  API     people and partners; every created staff member completes the forced
             password change through the API, so the server gate is exercised on
             every run and pass 3 can act as them
  3  API     leads as each field officer and as two dealers (the dealer's one-time
             code is read from the outbox by the owner, because nothing sends it yet:
             GAP-027)
  4  owner   spreads the timeline over the last 45 days, clamped to the current
             financial year, with the audit and updated_at triggers off for the
             duration of one transaction

The data lives in scripts/showcase_data.py.

**Every person it creates ends on one password**, the same `DEMO_PASSWORD` the
demo seed uses, with the forced first change already completed through the API.
So whoever is building against this can sign in as any of the nineteen and see
what that role sees, without changing a password first. The temporary password
each person holds in between is generated per run.

It refuses to write the published default password anywhere but a laptop;
`guard_passwords` in seed_demo.py is the check.
"""
from __future__ import annotations

import asyncio
import os
import random
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "local")

from scripts import showcase_data as data  # noqa: E402
from scripts.seed_demo import (  # noqa: E402
    DEMO_PASSWORD,
    ROOT_ORG_UNIT_ID,
    env,
    guard_passwords,
)

V1 = "/api/v1"
ADMIN_EMAIL = "admin@polysil.in"
# Generated per run, never published. Each person holds it for the one request
# between being created and completing the forced change, and it is the only
# credential in this script that was ever a reason to keep it off a real box.
TEMP_PASSWORD = "Tmp-" + secrets.token_urlsafe(18) + "-1a"
SHOWCASE_PASSWORD = DEMO_PASSWORD         # every showcase person ends with the demo password
LEAD_MOBILE_BASE = 9_800_100_000          # 98001xxxxx: never a real number in the demo
DEALER_LEADS = {"DLR-GONDAL": 6, "DLR-KESHOD": 4}   # created from the portal


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


class Api:
    """A signed-in caller. Raises on anything but the status it expected."""

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers

    async def get(self, path: str, **params: Any) -> Any:
        r = await self.client.get(f"{V1}{path}", params=params or None, headers=self.headers)
        if r.status_code != 200:
            raise SystemExit(f"GET {path} -> {r.status_code}: {r.text}")
        return r.json()

    async def post(self, path: str, body: Any = None, expect: int = 201) -> Any:
        r = await self.client.post(f"{V1}{path}", json=body, headers={**self.headers, **_key()})
        if r.status_code != expect:
            raise SystemExit(f"POST {path} {body} -> {r.status_code}: {r.text}")
        return r.json() if r.content else None

    async def patch(self, path: str, body: Any) -> Any:
        r = await self.client.patch(f"{V1}{path}", json=body, headers={**self.headers, **_key()})
        if r.status_code != 200:
            raise SystemExit(f"PATCH {path} {body} -> {r.status_code}: {r.text}")
        return r.json()

    async def page(self, path: str, **params: Any) -> list[dict]:
        """Every row of a keyset-paged list."""
        rows: list[dict] = []
        cursor = None
        while True:
            body = await self.get(path, limit=100, **({"cursor": cursor} if cursor else {}),
                                  **params)
            rows.extend(body["data"])
            cursor = body["meta"].get("next_cursor")
            if not cursor:
                return rows


async def _login(client: httpx.AsyncClient, email: str, password: str) -> Api | None:
    r = await client.post(f"{V1}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        return None
    return Api(client, {"Authorization": f"Bearer {r.json()['data']['access_token']}"})


# ── pass 0: the owner's sweep ────────────────────────────────────────────────

def _owner() -> psycopg.Connection:
    e = env()
    guard_passwords("seed_showcase")
    return psycopg.connect(host="127.0.0.1", port=6432, user=e["DB_USER"],
                           password=e["DB_PASSWORD"], dbname=e["DB_NAME"])


def _delete_leaves(cur: psycopg.Cursor, table: str, where: str) -> int:
    """Delete rows matching `where` that no child still points at, until none go."""
    total = 0
    while True:
        cur.execute(
            f"DELETE FROM {table} t WHERE {where} "
            f"AND NOT EXISTS (SELECT 1 FROM {table} c WHERE c.parent_id = t.id)")
        if cur.rowcount == 0:
            return total
        total += cur.rowcount


def pass_0_reset() -> None:
    """Sweep what the test fixtures left behind. **Local only.**

    Everything below matches a pytest fixture's naming (`api_`, `staff_`,
    `target_`, `API-`, a `Z` state code) and nothing a person would type, so on a
    box where the suite never runs it finds nothing. That is an argument, not a
    guarantee, and this is a delete pointed at a database someone else is building
    against: the frontend track's own data is not ours to reason about. It does
    not run outside local (GAP-098).
    """
    if (os.environ.get("ENVIRONMENT") or env().get("ENVIRONMENT") or "local") != "local":
        print("pass 0: skipped, not a local database")
        return
    old = "created_at < now() - interval '1 hour'"
    with _owner() as conn:
        cur = conn.cursor()
        # leads under the endpoint tests' coded states, then the states
        cur.execute(
            "SELECT id FROM territory WHERE level = 'state' AND code::text LIKE 'Z%' "
            f"AND (name LIKE 'gujarat\\_%' OR name LIKE 'api\\_state\\_%') AND {old}")
        states = [r[0] for r in cur.fetchall()]
        if states:
            cur.execute("SELECT id FROM territory WHERE parent_id = ANY(%s)", (states,))
            under = [r[0] for r in cur.fetchall()] + states
            cur.execute("DELETE FROM activity_event WHERE lead_id IN "
                        "(SELECT id FROM lead WHERE territory_id = ANY(%s))", (under,))
            cur.execute("DELETE FROM lead_duplicate_link WHERE lead_a_id IN "
                        "(SELECT id FROM lead WHERE territory_id = ANY(%s)) OR lead_b_id IN "
                        "(SELECT id FROM lead WHERE territory_id = ANY(%s))", (under, under))
            cur.execute("DELETE FROM notification_outbox WHERE recipient IN "
                        "(SELECT mobile FROM lead WHERE territory_id = ANY(%s))", (under,))
            cur.execute("DELETE FROM lead WHERE territory_id = ANY(%s)", (under,))
            cur.execute("DELETE FROM inquiry_counter WHERE state_code IN "
                        "(SELECT code::text FROM territory WHERE id = ANY(%s))", (states,))
        # people the test fixtures committed and did not remove
        cur.execute(
            "SELECT u.id FROM app_user u LEFT JOIN org_unit ou ON ou.id = u.org_unit_id "
            "LEFT JOIN channel_partner cp ON cp.id = u.partner_id "
            f"WHERE u.{old} AND (u.email::text LIKE 'staff\\_%@polysil.in' "
            "OR u.email::text LIKE 'target\\_%@polysil.in' OR ou.name LIKE 'api\\_%' "
            "OR cp.code::text LIKE 'API-%')")
        users = [r[0] for r in cur.fetchall()]
        made: dict[str, list] = {}
        if users:
            cur.execute("UPDATE lead SET owner_user_id = NULL WHERE owner_user_id = ANY(%s)",
                        (users,))
            cur.execute("DELETE FROM activity_event WHERE lead_id IN "
                        "(SELECT id FROM lead WHERE created_by = ANY(%s))", (users,))
            cur.execute("DELETE FROM lead WHERE created_by = ANY(%s)", (users,))
            # what those people created through the API carries created_by. Remember
            # it, clear every stamp (the FK), remove the people, then remove what they
            # created, leaves first
            for table in ("org_unit", "channel_partner", "territory"):
                cur.execute(f"SELECT id FROM {table} WHERE created_by = ANY(%s)", (users,))
                made[table] = [r[0] for r in cur.fetchall()]
                cur.execute(f"UPDATE {table} SET created_by = NULL, updated_by = NULL "
                            f"WHERE created_by = ANY(%s) OR updated_by = ANY(%s)", (users, users))
            cur.execute("UPDATE lead SET updated_by = NULL WHERE updated_by = ANY(%s)", (users,))
            cur.execute("UPDATE app_user SET created_by = NULL, updated_by = NULL WHERE "
                        "(created_by = ANY(%s) OR updated_by = ANY(%s)) AND NOT (id = ANY(%s))",
                        (users, users, users))
            for stmt in (
                # FS-010's tables first. A product carries created_by, so a user
                # the endpoint tests made and left behind cannot be deleted while
                # their products exist; price_list_item has no created_by of its
                # own and is reached through the list or the product that owns it.
                "DELETE FROM price_list_item i USING price_list l WHERE l.id = i.price_list_id "
                "AND (l.created_by = ANY(%s) OR l.created_by = ANY(%s))",
                "DELETE FROM price_list_item i USING product p "
                "WHERE p.id = i.product_id AND (p.created_by = ANY(%s) OR p.created_by = ANY(%s))",
                "DELETE FROM price_list WHERE created_by = ANY(%s) OR created_by = ANY(%s)",
                "DELETE FROM product_hsn h USING product p WHERE p.id = h.product_id "
                "AND (p.created_by = ANY(%s) OR p.created_by = ANY(%s))",
                "DELETE FROM product_hsn WHERE created_by = ANY(%s) OR created_by = ANY(%s)",
                "DELETE FROM gst_rate WHERE created_by = ANY(%s) OR created_by = ANY(%s)",
                "DELETE FROM seller_gstin WHERE created_by = ANY(%s) OR created_by = ANY(%s)",
                "DELETE FROM product WHERE created_by = ANY(%s) OR created_by = ANY(%s)",
                "DELETE FROM activity_event WHERE entity_id = ANY(%s) OR actor_id = ANY(%s)",
                "DELETE FROM session WHERE user_id = ANY(%s) OR user_id = ANY(%s)",
                "DELETE FROM user_territory WHERE user_id = ANY(%s) OR user_id = ANY(%s)",
                "DELETE FROM idempotency_record WHERE user_id = ANY(%s) OR user_id = ANY(%s)",
                "DELETE FROM login_attempt WHERE identifier IN (SELECT email::text FROM app_user "
                "WHERE id = ANY(%s) UNION SELECT mobile FROM app_user WHERE id = ANY(%s))",
                "DELETE FROM app_user WHERE id = ANY(%s) OR id = ANY(%s)",
            ):
                cur.execute(stmt, (users, users))
        free = {
            "org_unit": (
                "NOT EXISTS (SELECT 1 FROM org_unit c WHERE c.parent_id = t.id) "
                "AND NOT EXISTS (SELECT 1 FROM app_user u WHERE u.org_unit_id = t.id)"),
            "channel_partner": (
                "NOT EXISTS (SELECT 1 FROM channel_partner c WHERE c.parent_id = t.id) "
                "AND NOT EXISTS (SELECT 1 FROM app_user u WHERE u.partner_id = t.id)"),
            "territory": (
                "NOT EXISTS (SELECT 1 FROM territory c WHERE c.parent_id = t.id) "
                "AND NOT EXISTS (SELECT 1 FROM org_unit o WHERE o.territory_id = t.id) "
                "AND NOT EXISTS (SELECT 1 FROM channel_partner p WHERE p.territory_id = t.id) "
                "AND NOT EXISTS (SELECT 1 FROM lead l WHERE l.territory_id = t.id)"),
        }
        for table, ids in (made if users else {}).items():
            while ids:
                cur.execute(f"DELETE FROM {table} t WHERE t.id = ANY(%s) AND {free[table]} "
                            "RETURNING t.id", (ids,))
                gone = {r[0] for r in cur.fetchall()}
                if not gone:
                    break
                ids = [i for i in ids if i not in gone]
        cur.execute(f"DELETE FROM role_permission WHERE role_id IN (SELECT id FROM role "
                    f"WHERE code::text LIKE 'api\\_%' AND {old})")
        cur.execute(f"DELETE FROM role WHERE code::text LIKE 'api\\_%' AND {old}")
        n_p = _delete_leaves(cur, "channel_partner", f"t.code::text LIKE 'API-%' AND t.{old}")
        n_o = _delete_leaves(cur, "org_unit", f"t.name LIKE 'api\\_%' AND t.{old}")
        n_t = _delete_leaves(
            cur, "territory",
            f"(t.name LIKE 'api\\_%' OR t.name LIKE 'apid\\_%' OR t.name LIKE 'gujarat\\_%' "
            f"OR t.name LIKE 'gondal\\_%') AND t.{old}")
        conn.commit()
        print(f"pass 0: swept {len(users)} users, {n_p} partners, {n_o} offices, "
              f"{n_t} territories, {len(states)} test states")


# ── pass 1: territories and offices ──────────────────────────────────────────

async def pass_1_masters(admin: Api) -> dict[str, str]:
    """Returns name -> territory id for the state, every district, taluka and
    village the showcase uses, and name -> office id."""
    terr: dict[str, str] = {}
    state_name, state_code = data.STATE
    states = [t for t in await admin.page("/territories", level="state")
              if t["name"].lower() == state_name.lower()]
    if states:
        state = states[0]
        if state["code"] != state_code and not state["code_locked"]:
            state = (await admin.patch(f"/territories/{state['id']}", {"code": state_code}))["data"]
    else:
        state = (await admin.post("/territories", {"name": state_name, "level": "state",
                                                    "code": state_code}))["data"]
    terr[state_name] = state["id"]

    existing = {t["name"].lower(): t for t in await admin.page(
        "/territories", level="district", parent_id=state["id"])}
    created = 0
    for name, code in data.DISTRICTS:
        row = existing.get(name.lower())
        if row is None:
            row = (await admin.post("/territories", {
                "name": name, "level": "district", "parent_id": state["id"],
                "code": code}))["data"]
            created += 1
        terr[name] = row["id"]
    for district, talukas in data.TALUKAS.items():
        have = {t["name"].lower(): t for t in await admin.page(
            "/territories", level="taluka", parent_id=terr[district])}
        for taluka, villages in talukas.items():
            row = have.get(taluka.lower())
            if row is None:
                row = (await admin.post("/territories", {"name": taluka, "level": "taluka",
                                                          "parent_id": terr[district]}))["data"]
                created += 1
            terr[taluka] = row["id"]
            have_v = {t["name"].lower(): t for t in await admin.page(
                "/territories", level="village", parent_id=row["id"])}
            for village in villages:
                v = have_v.get(village.lower())
                if v is None:
                    v = (await admin.post("/territories", {"name": village, "level": "village",
                                                            "parent_id": row["id"]}))["data"]
                    created += 1
                terr[f"{taluka}/{village}"] = v["id"]
    print(f"pass 1: {created} territories created, {len(terr)} known")

    offices: dict[str, str] = {"Polysil HQ": ROOT_ORG_UNIT_ID}
    all_offices = await admin.page("/org-units")
    by_name = {o["name"].lower(): o for o in all_offices}
    created = 0
    for name, level, parent, territory in data.OFFICES:
        parent_id = offices[parent] if parent else None
        row = by_name.get(name.lower())
        if row is None:
            row = (await admin.post("/org-units", {
                "name": name, "role_level": level, "parent_id": parent_id,
                "territory_id": terr[territory] if territory else None}))["data"]
            created += 1
        else:
            patch: dict[str, Any] = {}
            current_parent = row["parent"]["id"] if row["parent"] else None
            if current_parent != parent_id:
                patch["parent_id"] = parent_id
            current_t = row["territory"]["id"] if row["territory"] else None
            if territory and current_t != terr[territory]:
                patch["territory_id"] = terr[territory]
            if patch:
                row = (await admin.patch(f"/org-units/{row['id']}", patch))["data"]
        offices[name] = row["id"]
    print(f"pass 1: {created} offices created, {len(offices)} known")
    return {**{f"t:{k}": v for k, v in terr.items()}, **{f"o:{k}": v for k, v in offices.items()}}


# ── pass 2: people and partners ──────────────────────────────────────────────

async def _complete_change(client: httpx.AsyncClient, email: str) -> None:
    """The forced-change flow, through the API, as the person."""
    me = await _login(client, email, TEMP_PASSWORD)
    if me is None:
        raise SystemExit(f"{email} is on a temporary password that is not the seed's; "
                         "reset it through POST /users/{id}/password and rerun")
    await me.post("/auth/password", {"current_password": TEMP_PASSWORD,
                                     "new_password": SHOWCASE_PASSWORD}, expect=204)


async def pass_2_people(client: httpx.AsyncClient, admin: Api, ids: dict[str, str]
                        ) -> tuple[dict[str, dict], dict[str, dict]]:
    people = await admin.page("/users")
    by_email = {p["email"]: p for p in people if p["email"]}
    by_name = {p["full_name"].lower(): p for p in people if p["user_type"] == "staff"}
    staff: dict[str, dict] = {}
    created = 0
    for local, name, role, office, territories in data.STAFF:
        email = f"{local}@polysil.in"
        row = by_email.get(email) or by_name.get(name.lower())
        wanted = {"role": role, "org_unit_id": ids[f"o:{office}"],
                  "territory_ids": [ids[f"t:{t}"] for t in territories]}
        if row is None:
            row = (await admin.post("/users", {"user_type": "staff", "full_name": name,
                                               "email": email, "password": TEMP_PASSWORD,
                                               **wanted}))["data"]
            created += 1
        else:
            detail = (await admin.get(f"/users/{row['id']}"))["data"]
            patch: dict[str, Any] = {}
            if detail["role"]["code"] != role:
                patch["role"] = role
            if (detail["org_unit"] or {}).get("id") != wanted["org_unit_id"]:
                patch["org_unit_id"] = wanted["org_unit_id"]
            if sorted(t["id"] for t in detail["territories"]) != sorted(wanted["territory_ids"]):
                patch["territory_ids"] = wanted["territory_ids"]
            if not detail["is_active"]:
                patch["is_active"] = True
            if patch and detail["id"] != admin_id(admin):
                row = (await admin.patch(f"/users/{row['id']}", patch))["data"]
            row = detail if not patch else row
        if row["must_change_password"]:
            await _complete_change(client, row["email"])
        staff[local] = row
    print(f"pass 2: {created} staff created, {len(staff)} known")

    partners: dict[str, dict] = {}
    existing = {p["code"].upper(): p for p in await admin.page("/partners")}
    created = 0
    for code, name, ptype, parent_code, district, user_name, mobile in data.PARTNERS:
        row = existing.get(code.upper())
        if row is None:
            row = (await admin.post("/partners", {
                "parent_id": partners[parent_code]["id"] if parent_code else None,
                "partner_type": ptype, "code": code, "name": name,
                "territory_id": ids[f"t:{district}"], "contact_name": user_name,
                "mobile": mobile}))["data"]
            created += 1
        partners[code] = row
        users = (await admin.get("/users", q=mobile, user_type="partner_user"))["data"]
        if not users:
            await admin.post("/users", {"user_type": "partner_user", "full_name": user_name,
                                        "mobile": mobile, "partner_id": row["id"]})
    print(f"pass 2: {created} partners created, {len(partners)} known")
    return staff, partners


_ADMIN_ID: dict[str, str] = {}


def admin_id(admin: Api) -> str:
    return _ADMIN_ID.get("id", "")


# ── pass 3: leads ────────────────────────────────────────────────────────────

def _read_otp(mobile: str) -> str:
    with _owner() as conn:
        cur = conn.cursor()
        cur.execute("SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = %s "
                    "ORDER BY created_at DESC LIMIT 1", (mobile,))
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"no one-time code in the outbox for {mobile}")
        return str(row[0])


async def _otp_login(client: httpx.AsyncClient, mobile: str) -> Api:
    await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    code = _read_otp(mobile)
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": code})
    if r.status_code != 200:
        raise SystemExit(f"OTP sign-in for {mobile} -> {r.status_code}: {r.text}")
    return Api(client, {"Authorization": f"Bearer {r.json()['data']['access_token']}"})


def _lead_body(rng: random.Random, i: int, territory_id: str, village: str) -> dict[str, Any]:
    system, itype, area, band = rng.choice(data.SYSTEM_MIX)
    hectares = round(rng.uniform(*area), 1)
    value = int(rng.uniform(*band))
    crop = rng.choice(data.CROPS)
    return {
        "farmer_name": f"{rng.choice(data.FARMER_FIRST)} {rng.choice(data.FARMER_LAST)}",
        "mobile": str(LEAD_MOBILE_BASE + i),
        "territory_id": territory_id, "village": village,
        "inquiry_type": itype, "mis_system": system,
        "estimated_value": f"{value}.00",
        "note": f"{crop}, about {hectares} Ha. {rng.choice(data.NOTES)}",
    }


async def _work_lead(caller: Api, lead: dict, stage: str, rng: random.Random,
                     lost_reason_id: str) -> None:
    lid = lead["id"]
    if stage == "new":
        return
    await caller.post(f"/leads/{lid}/transition", {"to_stage": "contacted"}, expect=200)
    await caller.post(f"/leads/{lid}/notes", {"note": rng.choice(data.NOTES)}, expect=201)
    if stage == "qualified":
        await caller.post(f"/leads/{lid}/transition", {"to_stage": "qualified"}, expect=200)
    elif stage == "lost":
        await caller.post(f"/leads/{lid}/transition",
                          {"to_stage": "lost", "lost_reason_id": lost_reason_id,
                           "lost_note": "Went with a local supplier."}, expect=200)


async def pass_3_leads(client: httpx.AsyncClient, admin: Api, ids: dict[str, str],
                       staff: dict[str, dict], partners: dict[str, dict]) -> None:
    rng = random.Random(2026)
    reasons = (await admin.get("/lookups/lost-reasons"))["data"]
    lost_reason_id = next(r["id"] for r in reasons if r["is_active"])
    # the field officers, their offices' talukas, and the villages under them
    officers = [(local, office) for local, _, role, office, _ in data.STAFF
                if role == "field_officer"]
    taluka_of_office = {o: o.replace(" Field", "") for _, o in officers}
    villages: dict[str, list[tuple[str, str]]] = {}
    for talukas in data.TALUKAS.values():
        for taluka, names in talukas.items():
            villages[taluka] = [(v, ids[f"t:{taluka}/{v}"]) for v in names]

    existing = {x["mobile"]: x for x in await admin.page("/leads")}
    created = 0
    sessions: dict[str, Api] = {}
    stages = list(data.STAGE_MIX)
    rng.shuffle(stages)
    for i, stage in enumerate(stages):
        mobile = "+91" + str(LEAD_MOBILE_BASE + i)
        if mobile in existing:
            continue
        local, office = officers[i % len(officers)]
        taluka = taluka_of_office[office]
        village, territory_id = rng.choice(villages[taluka])
        if local not in sessions:
            api = await _login(client, f"{local}@polysil.in", SHOWCASE_PASSWORD)
            if api is None:
                raise SystemExit(f"cannot sign in as {local}: run pass 2 first")
            sessions[local] = api
        lead = (await sessions[local].post(
            "/leads", _lead_body(rng, i, territory_id, village)))["data"]
        await _work_lead(sessions[local], lead, stage, rng, lost_reason_id)
        created += 1
    print(f"pass 3: {created} staff leads created")

    # the portal: two dealers enter leads, auto-assigned to the covering field officer
    offset = len(stages)
    created = 0
    for code, count in DEALER_LEADS.items():
        mobile = next(m for c, *_, m in data.PARTNERS if c == code)
        taluka = "Gondal" if code == "DLR-GONDAL" else "Keshod"
        dealer = None
        for j in range(count):
            i = offset + j
            lead_mobile = "+91" + str(LEAD_MOBILE_BASE + i)
            if lead_mobile in existing:
                continue
            if dealer is None:
                dealer = await _otp_login(client, mobile)
            village, territory_id = rng.choice(villages[taluka])
            await dealer.post("/leads", _lead_body(rng, i, territory_id, village))
            created += 1
        offset += count
    print(f"pass 3: {created} dealer leads created")

    # a merged pair and three duplicate pairs (one dismissed), from the same mobiles
    fo = sessions.get("ravi") or await _login(client, "ravi@polysil.in", SHOWCASE_PASSWORD)
    assert fo is not None
    dupes = [(offset + k, kind) for k, kind in enumerate(("merge", "dismiss", "keep", "keep"))]
    created = 0
    for i, kind in dupes:
        lead_mobile = "+91" + str(LEAD_MOBILE_BASE + i)
        # the default list hides merge losers, so one visible twin means the pair exists
        twins = [x for x in await admin.page("/leads", q=str(LEAD_MOBILE_BASE + i))
                 if x["mobile"] == lead_mobile]
        if twins:
            continue
        village, territory_id = rng.choice(villages["Gondal"])
        first = (await fo.post("/leads", _lead_body(rng, i, territory_id, village)))["data"]
        second_body = _lead_body(rng, i, territory_id, village)
        second_body["farmer_name"] = first["farmer_name"]
        second = (await fo.post("/leads", second_body))["data"]
        created += 2
        if kind == "merge":
            await fo.post(f"/leads/{second['id']}/merge", {"into_lead_id": first["id"]}, expect=200)
        elif kind == "dismiss":
            links = [d for d in (await fo.get("/leads/duplicates"))["data"]
                     if d["state"] == "pending"
                     and {d["lead_a"]["id"], d["lead_b"]["id"]} & {first["id"], second["id"]}]
            for link in links:
                await fo.post(f"/leads/duplicates/{link['link_id']}/dismiss", None, expect=200)
    print(f"pass 3: {created} leads created for the duplicate and merge pairs")


# ── pass 4: the timeline ─────────────────────────────────────────────────────

def _staff_emails() -> list[str]:
    return [f"{local}@polysil.in" for local, *_ in data.STAFF]


def _partner_mobiles() -> list[str]:
    return [mobile for *_, mobile in data.PARTNERS]


def _fy_start(now: datetime) -> datetime:
    """1 April IST of the current financial year, as UTC (FS-003 rule 2)."""
    ist = now + timedelta(hours=5, minutes=30)
    year = ist.year if ist.month >= 4 else ist.year - 1
    return datetime(year, 4, 1, tzinfo=UTC) - timedelta(hours=5, minutes=30)


def pass_4_timeline() -> None:
    now = datetime.now(UTC)
    start = max(now - timedelta(days=45), _fy_start(now))
    triggers = ["trg_lead_audit", "trg_lead_updated_at"]
    user_triggers = ["trg_app_user_audit_upd", "trg_app_user_updated_at"]
    rng = random.Random(45)
    with _owner() as conn:
        cur = conn.cursor()
        for t in triggers:
            cur.execute(f"ALTER TABLE lead DISABLE TRIGGER {t}")
        for t in user_triggers:
            cur.execute(f"ALTER TABLE app_user DISABLE TRIGGER {t}")
        # the showcase's own leads: its mobile block AND created by its own people
        # (cross-vendor P2-4: the block alone is a hundred thousand numbers)
        cur.execute("SELECT id FROM app_user WHERE email::text = ANY(%s) OR mobile = ANY(%s)",
                    (_staff_emails(), _partner_mobiles()))
        people = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT id, stage::text FROM lead WHERE mobile LIKE %s AND created_by = ANY(%s) "
            "ORDER BY created_at, id", (f"+91{str(LEAD_MOBILE_BASE)[:5]}%", people))
        leads = cur.fetchall()
        n = max(len(leads), 1)
        span = (now - timedelta(hours=2)) - start
        for k, (lid, stage) in enumerate(leads):
            created = start + span * (k / n) + timedelta(minutes=rng.randint(0, 240))
            created = min(created, now - timedelta(hours=2))   # early April: span is small
            contacted = created + timedelta(hours=rng.randint(2, 70)) if stage != "new" else None
            last = contacted or created
            if stage in ("qualified", "lost", "merged"):
                last = contacted + timedelta(days=rng.randint(1, 6))
            last = min(last, now - timedelta(minutes=30))
            cur.execute(
                "UPDATE lead SET created_at = %s, first_contacted_at = %s, last_activity_at = %s "
                "WHERE id = %s", (created, contacted, last, lid))
            cur.execute(
                "SELECT id, kind FROM activity_event WHERE lead_id = %s ORDER BY occurred_at, id",
                (lid,))
            events = cur.fetchall()
            step = (last - created) / max(len(events), 1)
            for j, (eid, kind) in enumerate(events):
                at = created if kind == "lead.created" else created + step * (j + 1)
                cur.execute("UPDATE activity_event SET occurred_at = %s WHERE id = %s", (at, eid))
        # only the showcase's own people: a test fixture's leftover is not ours to age
        cur.execute(
            "UPDATE app_user SET created_at = %s WHERE created_at > %s "
            "AND (email::text = ANY(%s) OR mobile = ANY(%s))",
            (start - timedelta(days=15), start, _staff_emails(), _partner_mobiles()))
        for t in triggers:
            cur.execute(f"ALTER TABLE lead ENABLE TRIGGER {t}")
        for t in user_triggers:
            cur.execute(f"ALTER TABLE app_user ENABLE TRIGGER {t}")
        conn.commit()
        print(f"pass 4: {len(leads)} leads spread from {start.date()} to {now.date()}")


# ── the report ───────────────────────────────────────────────────────────────

# a lead the seed owns: created by one of its people (the report's %(e)s / %(m)s)
OWN_LEAD = ("l.created_by IN (SELECT id FROM app_user WHERE email::text = ANY(%(e)s) "
            "OR mobile = ANY(%(m)s))")


def report() -> dict[str, object]:
    """Prints the shape and returns it; `--check` compares two runs (F-5)."""
    out: dict[str, object] = {}
    with _owner() as conn:
        cur = conn.cursor()
        for label, sql in (
            ("territories", "SELECT count(*) FROM territory WHERE deleted_at IS NULL"),
            ("offices (open)", "SELECT count(*) FROM org_unit WHERE deleted_at IS NULL"),
            ("org roots besides System",
             "SELECT count(*) FROM org_unit WHERE parent_id IS NULL AND deleted_at IS NULL "
             "AND name <> 'System'"),
            ("people (active)",
             "SELECT count(*) FROM app_user WHERE is_active AND deleted_at IS NULL"),
            ("people still on a temporary password",
             "SELECT count(*) FROM app_user WHERE must_change_password AND deleted_at IS NULL"),
            ("partners (active)", "SELECT count(*) FROM channel_partner WHERE is_active"),
            ("leads by stage",
             "SELECT string_agg(stage::text || ' ' || n, ', ' ORDER BY stage) FROM "
             "(SELECT stage, count(*) AS n FROM lead WHERE deleted_at IS NULL GROUP BY stage) s"),
            ("showcase people (active, changed their password)",
             "SELECT count(*) FROM app_user WHERE is_active AND deleted_at IS NULL "
             "AND NOT must_change_password AND (email::text = ANY(%(e)s) OR mobile = ANY(%(m)s))"),
            ("showcase leads",
             f"SELECT count(*) FROM lead l WHERE l.mobile LIKE '+91{str(LEAD_MOBILE_BASE)[:5]}%%' "
             "AND deleted_at IS NULL AND " + OWN_LEAD),
            ("showcase leads with one lead.created each",
             f"SELECT count(*) FROM lead l WHERE l.mobile LIKE '+91{str(LEAD_MOBILE_BASE)[:5]}%%' "
             "AND deleted_at IS NULL AND " + OWN_LEAD +
             " AND (SELECT count(*) FROM activity_event e "
             "WHERE e.lead_id = l.id AND e.kind = 'lead.created') = 1"),
            ("showcase leads numbered in the year they were created",
             f"SELECT count(*) FROM lead l WHERE l.mobile LIKE '+91{str(LEAD_MOBILE_BASE)[:5]}%%' "
             "AND deleted_at IS NULL AND " + OWN_LEAD +
             " AND split_part(l.inquiry_no::text, '/', 3) = "
             "to_char((l.created_at + interval '5 hours 30 minutes') - interval '3 months', "
             "'YYYY') || '-' || to_char((l.created_at + interval '5 hours 30 minutes') "
             "- interval '3 months' + interval '1 year', 'YY')"),
        ):
            params = {"e": _staff_emails(), "m": _partner_mobiles()} if "%(e)s" in sql else None
            cur.execute(sql, params)
            out[label] = cur.fetchone()[0]
            print(f"  {label}: {out[label]}")
    return out


async def _run() -> dict[str, object]:
    pass_0_reset()
    from api.main import app  # after ENVIRONMENT is set

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://showcase") as client:
        admin = await _login(client, ADMIN_EMAIL, DEMO_PASSWORD)
        if admin is None:
            raise SystemExit(f"cannot sign in as {ADMIN_EMAIL}: run scripts/seed_demo.py first")
        _ADMIN_ID["id"] = (await admin.get("/auth/me"))["data"]["id"]
        ids = await pass_1_masters(admin)
        staff, partners = await pass_2_people(client, admin, ids)
        await pass_3_leads(client, admin, ids, staff, partners)
    pass_4_timeline()
    return report()


SHOWCASE_KEYS = ("showcase people (active, changed their password)", "showcase leads",
                 "showcase leads with one lead.created each",
                 "showcase leads numbered in the year they were created")


async def main() -> None:
    """`--check` runs the seed twice and asserts section 10's seed row: the second
    run changes no showcase count, nobody is left on a temporary password, every
    showcase lead has one lead.created and is numbered in its own financial year."""
    first = await _run()
    if "--check" not in sys.argv:
        return
    print("\n--check: running again")
    second = await _run()
    problems = [f"{k}: {first[k]} then {second[k]}" for k in SHOWCASE_KEYS if first[k] != second[k]]
    if second["people still on a temporary password"]:
        problems.append("someone is still on a temporary password")
    if second["showcase leads"] != second["showcase leads with one lead.created each"]:
        problems.append("a showcase lead has zero or several lead.created events")
    if second["showcase leads"] != second["showcase leads numbered in the year they were created"]:
        problems.append("a showcase lead is numbered in another financial year")
    if problems:
        raise SystemExit("--check failed: " + "; ".join(problems))
    print("--check passed: a second run changed nothing")


if __name__ == "__main__":
    asyncio.run(main())
