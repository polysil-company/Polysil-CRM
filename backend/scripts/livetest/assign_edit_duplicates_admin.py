"""Live drive of slices 3 and 4 (assignment, edit, delete, duplicates, merge,
lookup admin) over HTTP with the seeded demo users. Not pytest."""
from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import psycopg

BASE = "http://127.0.0.1:8100/api/v1"
PW = "polysil-demo-2026"
ROOT = Path("D:/Polysil-CRM")
results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"\n         -> {detail}" if detail and not ok else ""))


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


E = env()


def key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


def staff_client(email: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=40)
    r = c.post("/auth/login", json={"email": email, "password": PW})
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


def dealer_client() -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=40)
    c.post("/auth/otp/request", json={"mobile": "919876543210"})
    with psycopg.connect(host="127.0.0.1", port=6432, user=E["DB_USER"],
                         password=E["DB_PASSWORD"], dbname=E["DB_NAME"]) as conn:
        code = conn.execute("SELECT payload->>'code' FROM notification_outbox "
                            "WHERE template_key='auth.otp' ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    r = c.post("/auth/otp/verify", json={"mobile": "919876543210", "code": code})
    if r.status_code != 200:
        # The request always answers 202, but only three codes are issued per phone
        # per 15 minutes (FS-001 rule 7). Running the three drivers back to back
        # spends them; the latest outbox row is then an old, burned code.
        raise SystemExit("dealer OTP did not verify: the 3-per-15-minutes burst limit "
                         "is probably spent. Wait 15 minutes and re-run.")
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


admin = staff_client("admin@polysil.in")
asha = staff_client("asha@polysil.in")
ravi = staff_client("ravi@polysil.in")
dealer = dealer_client()
me = {n: c.get("/auth/me").json()["data"] for n, c in
      (("admin", admin), ("asha", asha), ("ravi", ravi), ("dealer", dealer))}
GONDAL = next(t for t in asha.get("/lookups/territories", params={"q": "Gondal"}).json()["data"]
              if t["name"] == "Gondal")["id"]
PARTNER = me["dealer"]["partner"]["id"]


def make(client: httpx.Client, **over) -> dict:
    body = {"farmer_name": "Slice Farmer", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
            "territory_id": GONDAL, "inquiry_type": "commercial", "mis_system": "drip"}
    body.update(over)
    return client.post("/leads", json=body, headers=key()).json()["data"]


print("\n=== ASSIGNMENT ===")
a_ids = {a["id"] for a in asha.get("/leads/assignees").json()["data"]}
check("asha's assignee picker lists herself and ravi (her subtree), not the dealer",
      me["asha"]["id"] in a_ids and me["ravi"]["id"] in a_ids and me["dealer"]["id"] not in a_ids, str(a_ids))
ad_ids = {a["id"] for a in admin.get("/leads/assignees").json()["data"]}
check("admin's picker (global) includes asha and ravi", {me["asha"]["id"], me["ravi"]["id"]} <= ad_ids)
r = ravi.get("/leads/assignees")
check("ravi (own scope) gets an empty picker", r.status_code == 200 and r.json()["data"] == [])

lead = make(asha, farmer_name="Assign Me")
r = asha.post(f"/leads/{lead['id']}/assign", json={"owner_user_id": me["ravi"]["id"]}, headers=key())
check("asha assigns her lead to ravi -> 200, owner=ravi",
      r.status_code == 200 and r.json()["data"]["owner"]["id"] == me["ravi"]["id"], f"{r.status_code} {r.text[:160]}")
check("ravi now sees the lead (own scope keys on owner_user_id)",
      ravi.get(f"/leads/{lead['id']}").status_code == 200)
r = asha.post(f"/leads/{lead['id']}/assign", json={"assigned_partner_id": PARTNER}, headers=key())
check("asha assigns the demo dealer as partner -> 200",
      r.status_code == 200 and r.json()["data"]["assigned_partner"]["id"] == PARTNER, f"{r.status_code} {r.text[:160]}")
check("the dealer now sees the lead (partner_subtree)", dealer.get(f"/leads/{lead['id']}").status_code == 200)
r = ravi.post(f"/leads/{lead['id']}/assign", json={"owner_user_id": me["asha"]["id"]}, headers=key())
check("ravi (own scope) cannot name an owner -> 422", r.status_code == 422
      and "owner_user_id" in r.json()["error"].get("fields", {}), f"{r.status_code}")
r = asha.post(f"/leads/{lead['id']}/assign", json={"owner_user_id": None}, headers=key())
check("assign null clears the owner", r.status_code == 200 and r.json()["data"]["owner"] is None)

print("\n=== EDIT AND DELETE ===")
r = asha.patch(f"/leads/{lead['id']}", json={"farmer_name": "Corrected", "estimated_value": "250000.00",
                                             "mobile": "0 91234 56780"}, headers=key())
d = r.json().get("data", {})
check("asha PATCHes name, value, mobile (normalised) -> 200",
      r.status_code == 200 and d.get("farmer_name") == "Corrected" and d.get("estimated_value") == "250000.00"
      and d.get("mobile") == "+919123456780", f"{r.status_code} {r.text[:200]}")
other = make(asha, farmer_name="Not Ravis")
r = ravi.patch(f"/leads/{other['id']}", json={"village": "x"}, headers=key())
check("ravi PATCHing asha's lead -> 404", r.status_code == 404, f"{r.status_code}")
r = asha.delete(f"/leads/{other['id']}", headers=key())
check("asha (no leads.delete) DELETE -> 403", r.status_code == 403, f"{r.status_code}")
r = admin.delete(f"/leads/{other['id']}", headers=key())
check("admin (global, leads.delete) DELETE -> 204", r.status_code == 204, f"{r.status_code} {r.text[:120]}")
check("the deleted lead is hidden from asha (no leads.delete) -> 404",
      asha.get(f"/leads/{other['id']}").status_code == 404)
check("but still visible to admin (holds leads.delete) -> 200",
      admin.get(f"/leads/{other['id']}").status_code == 200)

print("\n=== DUPLICATES AND MERGE ===")
m = "98" + f"{uuid.uuid4().int % 10**8:08d}"
first = make(asha, mobile=m, farmer_name="Dup One")
second = make(asha, mobile=m, farmer_name="Dup Two")
check("second lead with the same mobile is flagged against the first",
      [x["lead_id"] for x in second["duplicates"]] == [first["id"]] and second["duplicates"][0]["signal"] == "mobile",
      str(second["duplicates"]))
q = asha.get("/leads/duplicates").json()["data"]
pair = next((p for p in q if {p["lead_a"]["id"], p["lead_b"]["id"]} == {first["id"], second["id"]}), None)
check("the pair is in asha's review queue", pair is not None)
check("ravi (sees neither lead) has an empty queue for that pair",
      all({p["lead_a"]["id"], p["lead_b"]["id"]} != {first["id"], second["id"]}
          for p in ravi.get("/leads/duplicates").json()["data"]))
r = asha.post(f"/leads/duplicates/{pair['link_id']}/dismiss", headers=key())
check("dismiss -> 200 and the pair leaves the queue", r.status_code == 200 and all(
    {p["lead_a"]["id"], p["lead_b"]["id"]} != {first["id"], second["id"]}
    for p in asha.get("/leads/duplicates").json()["data"]), f"{r.status_code}")

m2 = "98" + f"{uuid.uuid4().int % 10**8:08d}"
surv = make(asha, mobile=m2, farmer_name="Survivor")
loser = make(asha, mobile=m2, farmer_name="Loser")
r = dealer.post(f"/leads/{loser['id']}/merge", json={"into_lead_id": surv["id"]}, headers=key())
check("dealer cannot merge (staff only) -> 403 or 404", r.status_code in (403, 404), f"{r.status_code}")
r = asha.post(f"/leads/{loser['id']}/merge", json={"into_lead_id": surv["id"]}, headers=key())
check("asha merges loser into survivor -> 200 survivor", r.status_code == 200
      and r.json()["data"]["id"] == surv["id"], f"{r.status_code} {r.text[:160]}")
gone = asha.get(f"/leads/{loser['id']}").json()["data"]
check("loser is stage merged and points at the survivor",
      gone["stage"] == "merged" and gone["merged_into"]["id"] == surv["id"])
tl = [e["kind"] for e in asha.get(f"/leads/{surv['id']}/timeline").json()["data"]]
check("survivor's timeline folds in lead.merged and the loser's history",
      "lead.merged" in tl and tl.count("lead.created") >= 2, str(tl))
r = asha.post(f"/leads/{surv['id']}/merge", json={"into_lead_id": surv["id"]}, headers=key())
check("merge into itself -> 422 merge_self", r.status_code == 422 and r.json()["error"]["code"] == "merge_self")

print("\n=== LOOKUP ADMIN ===")
has_masters = any(p["module"] == "masters" and "edit" in p["actions"] for p in me["admin"]["permissions"])
code = "live_reason_" + uuid.uuid4().hex[:6]
r = admin.post("/lookups/lost-reasons", json={"code": code, "name": "Live reason"}, headers=key())
if has_masters:
    check("admin (masters.edit) adds a lost reason -> 201", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 201:
        rid = r.json()["data"]["id"]
        r2 = admin.patch(f"/lookups/lost-reasons/{rid}", json={"is_active": False}, headers=key())
        check("and switches it off -> 200 is_active=false", r2.status_code == 200 and r2.json()["data"]["is_active"] is False)
else:
    check("admin has no masters.edit in the matrix -> 403 on lookup admin", r.status_code == 403, f"{r.status_code}")
r = asha.post("/lookups/lost-reasons", json={"code": "x_" + uuid.uuid4().hex[:6], "name": "x"}, headers=key())
check("asha (no masters.edit) -> 403", r.status_code == 403, f"{r.status_code}")
sc = asha.get("/lookups/scoring")
check("scoring is readable by any signed-in user", sc.status_code == 200
      and {i["key"] for i in sc.json()["data"]} >= {"w_source", "threshold_hot"})

passed = sum(1 for ok, _, _ in results if ok)
print(f"\n=== SUMMARY: {passed}/{len(results)} passed ===")
for ok, n, _ in results:
    if not ok:
        print(f"  FAILED: {n}")
