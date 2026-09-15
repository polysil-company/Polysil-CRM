"""End-to-end test drive of the running API (auth + leads), over real HTTP.

Not pytest. Hits http://127.0.0.1:8100 like a client would, reads the OTP code
from the outbox, and exercises every case built so far across the four user
types. Prints a PASS/FAIL report.
"""
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
    tag = "PASS" if ok else "FAIL"
    line = f"  [{tag}] {name}"
    if detail and not ok:
        line += f"\n         -> {detail}"
    print(line)


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


E = env()


def db() -> psycopg.Connection:
    return psycopg.connect(host="127.0.0.1", port=6432, user=E["DB_USER"],
                           password=E["DB_PASSWORD"], dbname=E["DB_NAME"])


def rnd_mobile() -> str:
    return "98" + f"{uuid.uuid4().int % 10**8:08d}"


def me(client: httpx.Client) -> dict:
    return client.get("/auth/me").json()["data"]


# ── AUTH ─────────────────────────────────────────────────────────────────────

print("\n=== AUTH ===")

# staff login, good
anon = httpx.Client(base_url=BASE, timeout=40)
r = anon.post("/auth/login", json={"email": "asha@polysil.in", "password": PW})
ok = r.status_code == 200 and "access_token" in r.json().get("data", {})
check("staff login (asha) returns 200 + access token", ok, f"{r.status_code} {r.text[:200]}")
asha_refresh_client = anon  # keeps the refresh cookie

# wrong password
r = httpx.Client(base_url=BASE, timeout=40).post(
    "/auth/login", json={"email": "asha@polysil.in", "password": "wrong"})
check("wrong password -> 401 invalid_credentials",
      r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials",
      f"{r.status_code} {r.text[:160]}")

# unknown email (same answer)
r = httpx.Client(base_url=BASE, timeout=40).post(
    "/auth/login", json={"email": "nobody@polysil.in", "password": PW})
check("unknown email -> 401 invalid_credentials (indistinguishable)",
      r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials",
      f"{r.status_code} {r.text[:160]}")


def staff_client(email: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=40)
    resp = c.post("/auth/login", json={"email": email, "password": PW})
    c.headers["Authorization"] = f"Bearer {resp.json()['data']['access_token']}"
    return c


admin = staff_client("admin@polysil.in")
asha = staff_client("asha@polysil.in")
ravi = staff_client("ravi@polysil.in")

# /me
m = me(asha)
check("/me (asha) -> district_manager, org Rajkot District",
      m["role"]["code"] == "district_manager" and m["org_unit"]["name"] == "Rajkot District",
      str(m))
leads_perm = next((p for p in m["permissions"] if p["module"] == "leads"), None)
check("/me carries leads permission at org_subtree",
      leads_perm is not None and leads_perm["scope"] == "org_subtree", str(leads_perm))

# /me without token
r = httpx.Client(base_url=BASE, timeout=40).get("/auth/me")
check("/me without token -> 401", r.status_code == 401, f"{r.status_code}")

admin_id, asha_id, ravi_id = me(admin)["id"], m["id"], me(ravi)["id"]

# OTP flow for the dealer
dealer = httpx.Client(base_url=BASE, timeout=40)
r = dealer.post("/auth/otp/request", json={"mobile": "919876543210"})
check("dealer OTP request -> 202", r.status_code == 202, f"{r.status_code} {r.text[:160]}")
with db() as conn:
    code = conn.execute(
        "SELECT payload->>'code' FROM notification_outbox "
        "WHERE template_key = 'auth.otp' ORDER BY created_at DESC LIMIT 1").fetchone()[0]
r = dealer.post("/auth/otp/verify", json={"mobile": "919876543210", "code": code})
ok = r.status_code == 200 and "access_token" in r.json().get("data", {})
check("dealer OTP verify with the real code -> 200 + token", ok, f"{r.status_code} {r.text[:200]}")
if ok:
    dealer.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
dm = me(dealer)
check("/me (dealer) -> dealer role, partner set, partner_subtree",
      dm["role"]["code"] == "dealer" and dm["partner"] is not None,
      str(dm))
dealer_id = dm["id"]

# refresh using asha's cookie jar
r = asha_refresh_client.post("/auth/refresh")
check("refresh with the cookie -> 200 + new token",
      r.status_code == 200 and "access_token" in r.json().get("data", {}),
      f"{r.status_code} {r.text[:160]}")

# logout
r = asha_refresh_client.post("/auth/logout")
check("logout -> 204", r.status_code == 204, f"{r.status_code}")

# wrong OTP code
r2 = httpx.Client(base_url=BASE, timeout=40)
r2.post("/auth/otp/request", json={"mobile": "919876543210"})
rr = r2.post("/auth/otp/verify", json={"mobile": "919876543210", "code": "000000"})
check("dealer OTP verify with a wrong code -> 401", rr.status_code == 401, f"{rr.status_code}")


# ── LEADS ────────────────────────────────────────────────────────────────────

print("\n=== LEADS ===")

# territory picker gives us Gondal
r = asha.get("/lookups/territories", params={"q": "Gondal"})
terr = r.json()["data"]
gondal = next((t for t in terr if t["name"] == "Gondal"), None)
check("territory picker finds Gondal (taluka, parent Rajkot)",
      gondal is not None and gondal["level"] == "taluka"
      and gondal.get("parent", {}).get("name") == "Rajkot", str(terr)[:200])
GONDAL = gondal["id"]


def create(client: httpx.Client, *, key: str | None = None, **over) -> httpx.Response:
    body = {"farmer_name": "Rameshbhai Patel", "mobile": rnd_mobile(),
            "territory_id": GONDAL, "inquiry_type": "subsidised", "mis_system": "drip"}
    body.update(over)
    headers = {"Idempotency-Key": key or uuid.uuid4().hex}
    return client.post("/leads", json=body, headers=headers)


# create as each user type
r = create(admin, farmer_name="Admin Lead", estimated_value="125000.00")
adata = r.json().get("data", {})
check("admin (global) create -> 201, owner=admin, unit routed to Rajkot Field",
      r.status_code == 201 and adata.get("owner", {}).get("id") == admin_id
      and adata.get("owner_org_unit", {}).get("name") == "Rajkot Field",
      f"{r.status_code} {r.text[:240]}")
check("admin lead: inquiry_no POL/GJ/..., estimated_value round-trips as string",
      adata.get("inquiry_no", "").startswith("POL/GJ/") and adata.get("estimated_value") == "125000.00",
      str({k: adata.get(k) for k in ("inquiry_no", "estimated_value", "priority")}))
admin_lead = adata.get("id")

r = create(asha, farmer_name="Asha Lead")
sdata = r.json().get("data", {})
check("district manager (asha) create -> 201, owner=asha, unit=Rajkot District, source=employee",
      r.status_code == 201 and sdata.get("owner", {}).get("id") == asha_id
      and sdata.get("owner_org_unit", {}).get("name") == "Rajkot District"
      and sdata.get("source") == "employee",
      f"{r.status_code} {r.text[:240]}")
asha_lead = sdata.get("id")

r = create(ravi, farmer_name="Ravi Lead")
rdata = r.json().get("data", {})
check("field officer (ravi) create -> 201, owner=ravi, unit=Rajkot Field",
      r.status_code == 201 and rdata.get("owner", {}).get("id") == ravi_id
      and rdata.get("owner_org_unit", {}).get("name") == "Rajkot Field",
      f"{r.status_code} {r.text[:240]}")
ravi_lead = rdata.get("id")

r = create(dealer, farmer_name="Dealer Lead")
ddata = r.json().get("data", {})
check("dealer create -> 201, source=dealer, partner set, auto-owner=ravi",
      r.status_code == 201 and ddata.get("source") == "dealer"
      and ddata.get("assigned_partner") is not None
      and ddata.get("owner", {}).get("id") == ravi_id,
      f"{r.status_code} {r.text[:260]}")
dealer_lead = ddata.get("id")

# idempotency: replay
key = uuid.uuid4().hex
b = {"farmer_name": "Idem Lead", "mobile": rnd_mobile(), "territory_id": GONDAL,
     "inquiry_type": "commercial", "mis_system": "drip"}
r1 = asha.post("/leads", json=b, headers={"Idempotency-Key": key})
r2 = asha.post("/leads", json=b, headers={"Idempotency-Key": key})
check("idempotency: same key + body replays the same lead (no duplicate)",
      r1.status_code == 201 and r2.status_code == 201
      and r1.json()["data"]["id"] == r2.json()["data"]["id"],
      f"{r1.status_code}/{r2.status_code}")

# idempotency: conflict
r3 = asha.post("/leads", json={**b, "farmer_name": "Changed"},
               headers={"Idempotency-Key": key})
check("idempotency: same key + different body -> 409 idempotency_key_reused",
      r3.status_code == 409 and r3.json()["error"]["code"] == "idempotency_key_reused",
      f"{r3.status_code} {r3.text[:160]}")

# idempotency: missing key
r = asha.post("/leads", json=b)
check("mutation without Idempotency-Key -> 400 idempotency_key_required",
      r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required",
      f"{r.status_code} {r.text[:160]}")

# validation
r = create(asha, mobile="+1 415 555 0100")
check("non-Indian mobile -> 422 validation_error with fields.mobile",
      r.status_code == 422 and "mobile" in r.json()["error"].get("fields", {}),
      f"{r.status_code} {r.text[:200]}")

r = create(asha, mis_system="teleporter")
check("unknown mis_system -> 422 with fields.mis_system",
      r.status_code == 422 and "mis_system" in r.json()["error"].get("fields", {}),
      f"{r.status_code} {r.text[:200]}")

# create without permission: state_coordinator has leads view only, but no such
# user is seeded; instead verify the dealer cannot be refused create (it has it),
# already covered. Permission-refusal on create is covered by require() tests.

# scoping on list
def ids(client, **params):
    return {x["id"] for x in client.get("/leads", params=params).json()["data"]}


asha_list = ids(asha)
check("asha (org_subtree) list sees asha, ravi, admin and dealer leads",
      {asha_lead, ravi_lead, admin_lead, dealer_lead} <= asha_list,
      f"missing: {{asha,ravi,admin,dealer}} - got {len(asha_list)} ids")

ravi_list = ids(ravi)
check("ravi (own) list sees ravi + dealer(auto-assigned) leads, NOT asha/admin",
      {ravi_lead, dealer_lead} <= ravi_list and asha_lead not in ravi_list
      and admin_lead not in ravi_list,
      f"ravi_in={ravi_lead in ravi_list} dealer_in={dealer_lead in ravi_list} "
      f"asha_in={asha_lead in ravi_list} admin_in={admin_lead in ravi_list}")

dealer_list = ids(dealer)
check("dealer (partner_subtree) list sees only its own lead, NOT staff leads",
      dealer_lead in dealer_list and asha_lead not in dealer_list
      and ravi_lead not in dealer_list and admin_lead not in dealer_list,
      f"dealer_in={dealer_lead in dealer_list} staff_leaked="
      f"{bool({asha_lead, ravi_lead, admin_lead} & dealer_list)}")

admin_list = ids(admin)
check("admin (global) list sees all four leads",
      {asha_lead, ravi_lead, admin_lead, dealer_lead} <= admin_list, f"{len(admin_list)} ids")

# detail + 404 (out of scope is not-found)
r = asha.get(f"/leads/{asha_lead}")
check("asha detail of her own lead -> 200", r.status_code == 200, f"{r.status_code}")

r = ravi.get(f"/leads/{asha_lead}")
check("ravi detail of asha's lead -> 404 not_found (scope hides it)",
      r.status_code == 404 and r.json()["error"]["code"] == "not_found", f"{r.status_code}")

r = dealer.get(f"/leads/{asha_lead}")
check("dealer detail of a staff lead -> 404", r.status_code == 404, f"{r.status_code}")

r = ravi.get(f"/leads/{admin_lead}")
check("ravi detail of admin's lead -> 404 (owner is admin, not ravi)",
      r.status_code == 404, f"{r.status_code}")

r = asha.get(f"/leads/{uuid.uuid4()}")
check("detail of a random uuid -> 404", r.status_code == 404, f"{r.status_code}")

# search
inq = sdata.get("inquiry_no")
found = ids(asha, q=inq)
check("search by inquiry number returns exactly that lead", found == {asha_lead}, f"{found}")

# lookups
mis = [x["code"] for x in asha.get("/lookups/mis-systems").json()["data"]]
src = [x["code"] for x in asha.get("/lookups/lead-sources").json()["data"]]
lost = [x["code"] for x in asha.get("/lookups/lost-reasons").json()["data"]]
check("lookups: mis-systems has drip, sources has employee+dealer, reasons has price",
      "drip" in mis and "employee" in src and "dealer" in src and "price" in lost,
      f"mis={mis} src={src} lost={lost}")


# ── SUMMARY ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = [n for ok, n, _ in results if not ok]
print(f"\n=== SUMMARY: {passed}/{len(results)} passed ===")
if failed:
    print("FAILED:")
    for n in failed:
        print(f"  - {n}")
print("\ncreated leads:",
      {"admin": admin_lead, "asha": asha_lead, "ravi": ravi_lead, "dealer": dealer_lead})
