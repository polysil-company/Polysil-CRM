"""Live drive of the lead lifecycle (transition, reopen, notes, timeline) over HTTP,
with the seeded demo users. Not pytest."""
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
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


asha = staff_client("asha@polysil.in")
ravi = staff_client("ravi@polysil.in")
dealer = dealer_client()

GONDAL = next(t for t in asha.get("/lookups/territories", params={"q": "Gondal"}).json()["data"]
              if t["name"] == "Gondal")["id"]
LOST_REASON = asha.get("/lookups/lost-reasons").json()["data"][0]["id"]


def make(client: httpx.Client, **over) -> str:
    body = {"farmer_name": "Lifecycle Farmer", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
            "territory_id": GONDAL, "inquiry_type": "commercial", "mis_system": "drip"}
    body.update(over)
    return client.post("/leads", json=body, headers=key()).json()["data"]["id"]


def T(client: httpx.Client, lid: str, **body) -> httpx.Response:
    return client.post(f"/leads/{lid}/transition", json=body, headers=key())


print("\n=== LEAD LIFECYCLE (live, demo users) ===")

# happy path: asha walks a lead new -> contacted -> qualified -> lost -> reopen
lid = make(asha, note="met at Gondal mandi")
r = T(asha, lid, to_stage="contacted")
d = r.json()["data"]
check("asha: new -> contacted (200, first_contacted_at stamped)",
      r.status_code == 200 and d["stage"] == "contacted" and d["first_contacted_at"], f"{r.status_code} {r.text[:160]}")

r = T(asha, lid, to_stage="qualified")
check("asha: contacted -> qualified (200)", r.status_code == 200 and r.json()["data"]["stage"] == "qualified",
      f"{r.status_code} {r.text[:160]}")

r = T(asha, lid, to_stage="lost", lost_reason_id=LOST_REASON, lost_note="went with a competitor")
d = r.json()["data"]
check("asha: qualified -> lost (200, reason + note recorded)",
      r.status_code == 200 and d["stage"] == "lost" and d["lost_reason"]["id"] == LOST_REASON,
      f"{r.status_code} {r.text[:200]}")

r = asha.post(f"/leads/{lid}/reopen", json={"note": "farmer rang back"}, headers=key())
d = r.json()["data"]
check("asha: reopen lost -> back to qualified, reopen_count=1, reason cleared",
      r.status_code == 200 and d["stage"] == "qualified" and d["reopen_count"] == 1
      and d["lost_reason"] is None, f"{r.status_code} {r.text[:200]}")

# note + timeline
r = asha.post(f"/leads/{lid}/notes", json={"note": "call Monday"}, headers=key())
check("asha: add note -> 201 lead.note_added", r.status_code == 201 and r.json()["data"]["kind"] == "lead.note_added",
      f"{r.status_code} {r.text[:160]}")

tl = asha.get(f"/leads/{lid}/timeline").json()["data"]
kinds = [e["kind"] for e in tl]
check("timeline: newest-first, has created + stage changes + reopened + notes, actors named",
      kinds[0] == "lead.note_added" and "lead.created" in kinds and kinds.count("lead.stage_changed") == 3
      and "lead.reopened" in kinds and all(e["actor"] and e["actor"]["full_name"] for e in tl),
      f"kinds={kinds}")

# refusals
r = T(asha, make(asha), to_stage="won")
check("invalid move (new -> won) -> 422 invalid_transition", r.status_code == 422
      and r.json()["error"]["code"] == "invalid_transition", f"{r.status_code}")

lid2 = make(asha)
T(asha, lid2, to_stage="contacted"); T(asha, lid2, to_stage="qualified")
r = T(asha, lid2, to_stage="quoted")
check("qualified -> quoted -> 422 quotation_required", r.status_code == 422
      and r.json()["error"]["code"] == "quotation_required", f"{r.status_code}")

r = T(asha, make(asha), to_stage="lost")
check("lost without a reason -> 422 fields.lost_reason_id", r.status_code == 422
      and "lost_reason_id" in r.json()["error"].get("fields", {}), f"{r.status_code}")

lid3 = make(asha)
T(asha, lid3, to_stage="contacted")
r = T(asha, lid3, to_stage="qualified", expected_stage="new")
check("stale expected_stage -> 409 stage_changed (fields.stage=contacted)",
      r.status_code == 409 and r.json()["error"]["fields"]["stage"] == "contacted", f"{r.status_code}")

lid4 = make(asha)
T(asha, lid4, to_stage="lost", lost_reason_id=LOST_REASON)
r = T(asha, lid4, to_stage="contacted")
check("terminal (lost) lead cannot transition -> 422 stage_terminal", r.status_code == 422
      and r.json()["error"]["code"] == "stage_terminal", f"{r.status_code}")

# cross-user RLS on edit: ravi/dealer cannot transition asha's lead
r = T(ravi, lid, to_stage="contacted")
check("ravi cannot transition asha's lead -> 404 (edit scope hides it)", r.status_code == 404, f"{r.status_code}")
r = T(dealer, lid, to_stage="contacted")
check("dealer cannot transition a staff lead -> 404", r.status_code == 404, f"{r.status_code}")

# but each can work their own
rl = make(ravi)
r = T(ravi, rl, to_stage="contacted")
check("ravi transitions his OWN lead -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

dl = make(dealer)
r = T(dealer, dl, to_stage="contacted")
check("dealer transitions its OWN lead -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

# idempotency on a transition: same key replays, no double-apply
lid5 = make(asha)
k = key()
a = asha.post(f"/leads/{lid5}/transition", json={"to_stage": "contacted"}, headers=k)
b = asha.post(f"/leads/{lid5}/transition", json={"to_stage": "contacted"}, headers=k)
check("transition idempotency: same key replays (both 200, same stage)",
      a.status_code == 200 and b.status_code == 200 and b.json()["data"]["stage"] == "contacted",
      f"{a.status_code}/{b.status_code}")

r = asha.post(f"/leads/{lid5}/transition", json={"to_stage": "contacted"})
check("transition without Idempotency-Key -> 400", r.status_code == 400
      and r.json()["error"]["code"] == "idempotency_key_required", f"{r.status_code}")

# timeline 404 for a lead the caller cannot see
r = ravi.get(f"/leads/{lid}/timeline")
check("ravi timeline of asha's lead -> 404", r.status_code == 404, f"{r.status_code}")

passed = sum(1 for ok, _, _ in results if ok)
failed = [n for ok, n, _ in results if not ok]
print(f"\n=== SUMMARY: {passed}/{len(results)} passed ===")
for n in failed:
    print(f"  FAILED: {n}")
