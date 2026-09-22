#!/usr/bin/env python3
"""Generate docs/flows/*.excalidraw from declarative flow definitions.

Open them at excalidraw.com or in the VS Code Excalidraw extension. They are
editable - move things about, add notes; regenerating overwrites, so keep
hand edits in a copy if you want them to survive.

    python scripts/generate_flows.py

Detail belongs ON the canvas, not in a separate document. Anything worth
knowing about a step is a note beside that step.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "flows"

INK = "#1e1e1e"
BLUE, GREEN, RED, YELLOW, VIOLET, GREY = (
    "#1971c2", "#2f9e44", "#e03131", "#f08c00", "#6741d9", "#868e96")
FILL = {BLUE: "#a5d8ff", GREEN: "#b2f2bb", RED: "#ffc9c9",
        YELLOW: "#ffec99", VIOLET: "#d0bfff", GREY: "#e9ecef", INK: "transparent"}

_seed = random.Random(20260907)


def _nonce() -> int:
    return _seed.randint(10**8, 10**9)


def _base(eid: str, x: float, y: float, w: float, h: float, colour: str) -> dict:
    return {
        "id": eid, "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": colour, "backgroundColor": FILL.get(colour, "transparent"),
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "seed": _nonce(), "version": 1, "versionNonce": _nonce(),
        "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }


def node(eid, x, y, label, w=210, h=70, colour=BLUE, shape="rectangle", size=16):
    box = _base(eid, x, y, w, h, colour)
    box["type"] = shape
    box["roundness"] = {"type": 3} if shape == "rectangle" else None
    tid = f"{eid}__t"
    box["boundElements"] = [{"id": tid, "type": "text"}]
    lines = label.split("\n")
    th = len(lines) * size * 1.25
    txt = _base(tid, x + 8, y + (h - th) / 2, w - 16, th, INK)
    txt.update({
        "type": "text", "text": label, "fontSize": size, "fontFamily": 2,
        "textAlign": "center", "verticalAlign": "middle", "containerId": eid,
        "originalText": label, "lineHeight": 1.25, "autoResize": True,
        "backgroundColor": "transparent",
    })
    return [box, txt]


def note(eid, x, y, text, w=300, colour=GREY, size=13):
    """Free text on the canvas - the 'more to read', placed where it applies."""
    lines = text.split("\n")
    h = len(lines) * size * 1.35
    t = _base(eid, x, y, w, h, colour)
    t.update({
        "type": "text", "text": text, "fontSize": size, "fontFamily": 2,
        "textAlign": "left", "verticalAlign": "top", "containerId": None,
        "originalText": text, "lineHeight": 1.35, "autoResize": True,
        "backgroundColor": "transparent", "strokeColor": colour,
    })
    return [t]


def edge(eid, a: dict, b: dict, label: str = "", colour=INK, dashed=False):
    """Straight arrow from element a to element b, bound at both ends."""
    ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
    bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    dx, dy = bx - ax, by - ay
    ar = _base(eid, ax, ay, abs(dx), abs(dy), colour)
    ar.update({
        "type": "arrow", "points": [[0, 0], [dx, dy]],
        "startBinding": {"elementId": a["id"], "focus": 0, "gap": 6},
        "endBinding": {"elementId": b["id"], "focus": 0, "gap": 6},
        "lastCommittedPoint": None, "startArrowhead": None, "endArrowhead": "arrow",
        "roundness": {"type": 2}, "elbowed": False,
        "backgroundColor": "transparent",
        "strokeStyle": "dashed" if dashed else "solid",
    })
    a.setdefault("boundElements", []).append({"id": eid, "type": "arrow"})
    b.setdefault("boundElements", []).append({"id": eid, "type": "arrow"})
    out = [ar]
    if label:
        lid = f"{eid}__l"
        lt = _base(lid, ax + dx / 2 - 40, ay + dy / 2 - 20, 80, 18, colour)
        lt.update({
            "type": "text", "text": label, "fontSize": 12, "fontFamily": 2,
            "textAlign": "center", "verticalAlign": "middle", "containerId": None,
            "originalText": label, "lineHeight": 1.25, "autoResize": True,
            "backgroundColor": "transparent",
        })
        out.append(lt)
    return out


STAMP = "internal build"


def title(text, x=0, y=-90, sub="", status="", status_colour=GREY):
    """status is what is BUILT, not what is designed. A canvas with no status
    line is a canvas nobody has checked since it was drawn."""
    els = note("title", x, y, text, colour=INK, size=28)
    if sub:
        els += note("subtitle", x, y + 42, sub, colour=GREY, size=14)
    if status:
        els += note("status", x, y + 68, f"{STAMP}   {status}",
                    colour=status_colour, size=13)
    return els


def write(name: str, elements: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "type": "excalidraw", "version": 2,
        "source": "polysil-crm/scripts/generate_flows.py",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    (OUT / f"{name}.excalidraw").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"  {name}.excalidraw  ({len(elements)} elements)")


# ══════════════════════════════════════════════════════════════════════
def f_system() -> None:
    e, n = [], {}
    e += title("Polysil CRM - the whole system",
               sub="Lead to cash, with the subsidy branch. Every box is a module.",
               status="DESIGN. Built: auth, both trees. No business table exists yet.",
               status_colour=RED)

    row = [("lead", 0, "LEAD", GREEN), ("quote", 260, "QUOTATION", BLUE),
           ("order", 520, "SALES ORDER", BLUE), ("disp", 780, "DISPATCH", BLUE),
           ("comp", 1040, "COMPLAINT", RED)]
    for eid, x, lbl, c in row:
        els = node(eid, x, 60, lbl, colour=c)
        n[eid] = els[0]; e += els

    for eid, x, lbl in [("wa", -300, "WhatsApp"), ("web", -300, "Website form"),
                        ("qr", -300, "QR code"), ("emp", -300, "Employee / Dealer")]:
        pass
    for i, (eid, lbl) in enumerate([("wa", "WhatsApp"), ("web", "Website form"),
                                    ("qr", "QR code"), ("emp", "Employee / Dealer")]):
        els = node(eid, -300, -40 + i * 62, lbl, w=190, h=48, colour=GREY, size=14)
        n[eid] = els[0]; e += els
        e += edge(f"e_{eid}", n[eid], n["lead"], colour=GREY)

    for a, b in [("lead", "quote"), ("quote", "order"), ("order", "disp"), ("disp", "comp")]:
        e += edge(f"e_{a}_{b}", n[a], n[b])

    els = node("repl", 1040, 220, "REPLACEMENT\norder", colour=RED); n["repl"] = els[0]; e += els
    e += edge("e_c_r", n["comp"], n["repl"], "QC approved")

    els = node("sub", 260, 260, "SUBSIDY APPLICATION\n17 stages, manual entry",
               w=300, h=80, colour=VIOLET); n["sub"] = els[0]; e += els
    e += edge("e_q_s", n["quote"], n["sub"], "if subsidised", VIOLET, dashed=True)

    els = node("fp", 660, 260, "DEPARTMENT\nfinal payment", w=220, h=80, colour=VIOLET)
    n["fp"] = els[0]; e += els
    e += edge("e_s_fp", n["sub"], n["fp"], colour=VIOLET)

    els = node("pay", 780, 400, "RECEIPTS\nallocations, adjustments",
               w=280, h=80, colour=YELLOW); n["pay"] = els[0]; e += els
    e += edge("e_d_p", n["disp"], n["pay"], colour=YELLOW, dashed=True)

    e += note("n1", -300, 220,
              "PUBLIC CAPTURE never touches `lead` directly.\n"
              "One SECURITY DEFINER function writes to\n"
              "lead_intake; a worker does dedupe, numbering,\n"
              "assignment and scoring.\n\n"
              "The public role holds EXECUTE on that function\n"
              "and NO table grants at all.", w=330)
    e += note("n2", 1040, 340,
              "Complaint -> manager -> QC -> replacement.\n"
              "Replacement orders carry zero value and\n"
              "require an approved complaint.", w=300, colour=RED)
    e += note("n3", 260, 380,
              "THREE calculation models, one per system.\n"
              "Drip and Mini Sprinkler: 7 cost blocks, 2-D Jantri.\n"
              "Sprinkler: field+inspection only, 1-D exact lookup,\n"
              "quantities derived from area, no head unit.", w=380, colour=VIOLET)
    e += note("n4", 780, 500,
              "DEFERRED to Phase 2. Orders and dispatch ship;\n"
              "recording receipts against them does not.", w=300, colour=YELLOW)
    write("01-system-overview", e)


def f_request() -> None:
    e, n = [], {}
    e += title("Request lifecycle",
               sub="One transaction per request. The claim is set inside it, never outside.",
               status="BUILT: every step. Both enforcers land in FS-002 (migration 005).",
               status_colour=GREEN)
    steps = [
        ("c", "Client\nBearer + Idempotency-Key", GREY),
        ("r", "Router\nparse, call service", BLUE),
        ("d", "deps.py\nBEGIN + set_config(..., true)", RED),
        ("rq", "require()\napp_has_permission() in the DB\n403 or continue", BLUE),
        ("s", "Service  -  ENFORCER 1\nscope predicate + every parent id\nfrom the module's ScopeSpec", VIOLET),
        ("dom", "domain/\npure functions, no I/O", GREEN),
        ("pg", "Postgres  -  ENFORCER 2\nRLS re-checks the same rule\n61 policies from the same ScopeSpec", VIOLET),
        ("cm", "COMMIT\nbefore the response is sent", GREEN),
    ]
    for i, (eid, lbl, c) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=300, h=80, colour=c)
        n[eid] = els[0]; e += els
        if i:
            e += edge(f"e{i}", n[steps[i-1][0]], n[eid])

    els = node("w3", 430, 860, "row + activity_event\n+ outbox  (ONE txn)", w=260, h=80, colour=GREEN)
    n["w3"] = els[0]; e += els
    e += edge("e_pg_w3", n["cm"], n["w3"], colour=GREEN)

    e += note("nA", 380, 235,
              "THE MOST IMPORTANT LINE IN THE CODEBASE\n\n"
              "set_config('app.current_user_id', ..., true)\n\n"
              "The trailing true makes it transaction-scoped.\n"
              "A plain SET leaves the claim on the connection.\n"
              "The next request to borrow that connection then\n"
              "runs as the WRONG USER.\n\n"
              "Invisible under light load. A test drives the real\n"
              "dependency over a pooled connection and fails if\n"
              "the true becomes false.", w=430, colour=RED)
    e += note("nB", 380, 455,
              "TWO ENFORCERS  (ADR-039)\n\n"
              "The service checks scope itself and refuses on its\n"
              "own authority. RLS checks the same rule again.\n"
              "Neither layer trusts the other.\n\n"
              "Step 5 also validates every parent id in the body.\n"
              "RLS cannot do that: a foreign key reference is not\n"
              "policy-filtered, so it points at rows the caller\n"
              "cannot read.", w=430, colour=VIOLET)
    e += note("nC", 380, 625,
              "domain/ never imports SQLAlchemy.\n"
              "GST, discounts, subsidy and scoring are pure.\n"
              "Thousands of cases run in under a second, which\n"
              "is the only reason they get run every time.", w=400, colour=GREEN)
    e += note("nD", 380, 715,
              "Every transaction switches into app_role after the\n"
              "claim: set_config('role', ..., true). The owner is\n"
              "exempt from every policy, so this line is what makes\n"
              "the 61 policies apply. The parity suite runs as\n"
              "app_role and has a check that fails as the owner.",
              w=430, colour=GREEN)
    e += note("nE", 380, 845,
              "scope=\"function\" on the dependency.\n"
              "Without it the COMMIT runs AFTER the response,\n"
              "so a failed commit cannot change the answer.\n"
              "A logout would return 204 having revoked nothing.",
              w=410, colour=GREEN)
    e += note("nF", 430, 980,
              "All three rows in one transaction, or none.\n"
              "That is what stops a cancelled order\n"
              "sending a confirmation.", w=320, colour=GREEN)
    write("02-request-lifecycle", e)


def f_permissions() -> None:
    e, n = [], {}
    e += title("Who can see what",
               sub="Two independent trees. Five scopes. Exactly one branch matches.",
               status="BUILT. Both trees, 61 policies (005), 1,600-cell matrix, per-branch parity.",
               status_colour=GREEN)

    staff = ["Field Officer", "District Manager", "State Manager",
             "Regional Manager", "Admin-Sales / MD / CEO"]
    for i, lbl in enumerate(staff):
        eid = f"s{i}"
        els = node(eid, 0, i * 95, lbl, w=250, h=62, colour=BLUE, size=14)
        n[eid] = els[0]; e += els
        if i:
            e += edge(f"es{i}", n[f"s{i-1}"], n[eid], colour=BLUE)

    for i, lbl in enumerate(["Distributor", "Dealer", "Sub-dealer"]):
        eid = f"p{i}"
        els = node(eid, 400, i * 95, lbl, w=220, h=62, colour=GREEN, size=14)
        n[eid] = els[0]; e += els
        if i:
            e += edge(f"ep{i}", n[f"p{i-1}"], n[eid], colour=GREEN)

    for i, lbl in enumerate(["Account Mgr", "Dispatch Mgr", "QC Mgr", "State Co-ordinator"]):
        eid = f"h{i}"
        els = node(eid, 760, i * 78, lbl, w=210, h=56, colour=YELLOW, size=14)
        n[eid] = els[0]; e += els

    e += note("l1", 0, -40, "STAFF  -  org_closure", colour=BLUE, size=16)
    e += note("l2", 400, -40, "CHANNEL  -  partner_closure", colour=GREEN, size=16)
    e += note("l3", 760, -40, "OUTSIDE BOTH  -  HQ nodes", colour=YELLOW, size=16)

    e += note("sc", 0, 520,
              "THE FIVE SCOPES\n\n"
              "own              rows the user owns            Field Officer\n"
              "org_subtree      their subtree in org_closure  District/State/Regional\n"
              "territory        via user_territory            State Co-ordinator\n"
              "partner_subtree  their partner subtree         Distributor/Dealer/Sub\n"
              "global           everything, if permitted      Admin, MD, functional mgrs",
              w=620, colour=INK, size=13)
    e += note("sc2", 700, 520,
              "EVERY permissive branch tests the scope it serves.\n"
              "Scope is one value per (role, module), so exactly\n"
              "one branch can be true. Mutually exclusive by\n"
              "construction, not by hope.\n\n"
              "Permissive policies GRANT (OR'd together).\n"
              "Restrictive policies NARROW (AND'd).\n"
              "Adding a narrower permissive policy narrows nothing.\n\n"
              "Visibility and the approval queue are SEPARATE.\n"
              "A District Manager sees every record in the\n"
              "district. The queue is the subset waiting on them.",
              w=440, colour=RED)
    e += note("sc4", 0, 700,
              "THE STANCE CHANGED  (ADR-039)\n\n"
              "Before: the API check was only there to return a clean\n"
              "403 instead of an empty list. RLS was the boundary.\n\n"
              "Now: two enforcers. The service owns security and\n"
              "refuses on its own authority. RLS checks the same rule\n"
              "underneath. Neither assumes the other is correct.\n\n"
              "Why one layer is not enough:\n"
              "  - a foreign key reference is NOT policy-filtered, so\n"
              "    it is an existence oracle and lets a user attach a\n"
              "    row to a parent they cannot read. No policy fixes it.\n"
              "  - a forgotten ENABLE opens one table and nothing fails,\n"
              "    because the symptom is MORE rows, not fewer.\n"
              "  - RLS cannot tell 'you may not' from 'there is nothing'.\n"
              "    The UI needs both answers.\n\n"
              "Cost: one rule, two implementations. Paid for by one\n"
              "ScopeSpec per module that emits both, plus a parity\n"
              "suite asserting the two layers agree on all 1,600 cells.",
              w=560, colour=VIOLET)
    e += note("sc5", 620, 830,
              "STILL TRUE, unchanged by ADR-039:\n"
              "  - hiding a button is not authorization\n"
              "  - the API never reads a role off the token\n"
              "    (ADR-038: no role claim is issued at all)\n\n"
              "16 roles x 20 modules x 5 actions = 1,600.\n"
              "Not 1,440 - that count drops campaigns and\n"
              "stock, which appear in only one matrix each.",
              w=460, colour=YELLOW)
    e += note("sc3", 760, 340,
              "HQ nodes have no sales descendants,\n"
              "so their reach comes from scope,\n"
              "never from closure descent.", w=300, colour=YELLOW)
    write("03-permissions", e)


def f_lead() -> None:
    e, n = [], {}
    e += title("Lead capture", sub="Public capture never touches `lead` directly.",
               status="BUILT. FS-003: manual entry, lifecycle, assignment, duplicates, "
                      "lookup admin. Other capture sources adapt onto it later.",
               status_colour=RED)

    for i, (eid, lbl) in enumerate([("web", "Website form"), ("qr", "QR code"),
                                    ("wa", "WhatsApp inbound"), ("meta", "Meta / Google\n(later)")]):
        els = node(eid, 0, i * 80, lbl, w=200, h=60, colour=GREY, size=14)
        n[eid] = els[0]; e += els

    els = node("fn", 300, 100, "intake_submit()\nSECURITY DEFINER", w=250, h=80, colour=RED)
    n["fn"] = els[0]; e += els
    for eid in ("web", "qr", "wa", "meta"):
        e += edge(f"e_{eid}_fn", n[eid], n["fn"], colour=GREY)

    els = node("tbl", 640, 100, "lead_intake\nappend-only", w=220, h=80, colour=YELLOW)
    n["tbl"] = els[0]; e += els
    e += edge("e_fn_tbl", n["fn"], n["tbl"])

    els = node("wk", 950, 100, "worker\nclaim + process", w=220, h=80, colour=VIOLET)
    n["wk"] = els[0]; e += els
    e += edge("e_tbl_wk", n["tbl"], n["wk"])

    chain = [("dup", "Duplicate check\nflag, never block"),
             ("num", "Inquiry number\nPOL/GJ/2026-27/00123"),
             ("asg", "Assign +\nderive senior manager"),
             ("scr", "Score\nhot / warm / cold")]
    for i, (eid, lbl) in enumerate(chain):
        els = node(eid, 950, 240 + i * 100, lbl, w=260, h=76, colour=BLUE, size=14)
        n[eid] = els[0]; e += els
        e += edge(f"e_ch{i}", n["wk"] if i == 0 else n[chain[i-1][0]], n[eid], colour=BLUE)

    els = node("lead", 950, 660, "LEAD  +  activity_event\n+ thank-you outbox row",
               w=300, h=80, colour=GREEN)
    n["lead"] = els[0]; e += els
    e += edge("e_scr_lead", n["scr"], n["lead"], colour=GREEN)

    els = node("man", 640, 660, "Manual entry\n(CRM / portal)", w=210, h=70, colour=GREY, size=14)
    n["man"] = els[0]; e += els
    e += edge("e_man", n["man"], n["lead"], colour=GREY, dashed=True)

    e += note("n1", 300, 220,
              "The public role holds EXECUTE on this\n"
              "function and NO table grants at all.\n\n"
              "It returns only id / status / replayed -\n"
              "never the payload, so it cannot be used\n"
              "to probe whether a number is known.", w=310, colour=RED)
    e += note("n2", 620, 220,
              "THREE unique indexes, by what the\n"
              "transport actually provides:\n\n"
              "  source_event_id   (11za, Meta)\n"
              "  idempotency_key   (our own form)\n"
              "  payload_hash + UTC hour  (bare post)\n\n"
              "Same key + different payload -> 409.\n"
              "The hour bucket is a GENERATED column:\n"
              "date_trunc on timestamptz is not\n"
              "IMMUTABLE and Postgres rejects it.", w=330, colour=YELLOW)
    e += note("n3", 1260, 240,
              "BUSINESS duplication (same farmer enquiring\n"
              "twice) is real and allowed - flagged for a\n"
              "human, never blocked. A blocked enquiry is\n"
              "a lost enquiry.\n\n"
              "TRANSPORT duplication (a retried submission)\n"
              "is suppressed silently. Two different things.", w=380, colour=VIOLET)
    e += note("n4", 1260, 460,
              "Claim uses FOR UPDATE SKIP LOCKED and\n"
              "reclaims STALE 'processing' rows, not just\n"
              "'pending' - otherwise a worker dying after\n"
              "its claim commits strands the enquiry.\n\n"
              "claim_token stops a resurrected worker\n"
              "overwriting a row someone else reclaimed.", w=390, colour=VIOLET)
    write("04-lead-capture", e)


def f_approval() -> None:
    e, n = [], {}
    e += title("Approval routing", sub="One engine, three chains, thresholds as data.",
               status="DESIGN ONLY (RBAC.md 5.2a-5.2f). No code. W3-W4.",
               status_colour=RED)

    els = node("r", 0, 120, "Raiser\nemployee or dealer", w=220, h=70, colour=GREY, size=14)
    n["r"] = els[0]; e += els

    els = node("d1", 300, 120, "<= X ?", w=140, h=90, colour=YELLOW, shape="diamond")
    n["d1"] = els[0]; e += els
    e += edge("e_r_d1", n["r"], n["d1"])

    els = node("dm", 520, 20, "District Mgr\napproves", w=200, h=64, colour=GREEN, size=14)
    n["dm"] = els[0]; e += els
    e += edge("e_d1_dm", n["d1"], n["dm"], "yes", GREEN)

    els = node("d2", 520, 200, "<= Y ?", w=140, h=90, colour=YELLOW, shape="diamond")
    n["d2"] = els[0]; e += els
    e += edge("e_d1_d2", n["d1"], n["d2"], "no", RED)

    els = node("sm", 760, 120, "State Mgr\napproves", w=200, h=64, colour=GREEN, size=14)
    n["sm"] = els[0]; e += els
    e += edge("e_d2_sm", n["d2"], n["sm"], "yes", GREEN)

    els = node("rm", 760, 300, "Regional Mgr\napproves", w=200, h=64, colour=GREEN, size=14)
    n["rm"] = els[0]; e += els
    e += edge("e_d2_rm", n["d2"], n["rm"], "no", RED)

    els = node("t", 1040, 160, "document\ntype?", w=150, h=95, colour=YELLOW, shape="diamond", size=14)
    n["t"] = els[0]; e += els
    for a in ("dm", "sm", "rm"):
        e += edge(f"e_{a}_t", n[a], n["t"], colour=GREEN)

    els = node("ac", 1280, 40, "Account Mgr", w=190, h=60, colour=BLUE, size=14)
    n["ac"] = els[0]; e += els
    els = node("dp", 1520, 40, "Dispatch Mgr", w=190, h=60, colour=BLUE, size=14)
    n["dp"] = els[0]; e += els
    e += edge("e_t_ac", n["t"], n["ac"], "order", BLUE)
    e += edge("e_ac_dp", n["ac"], n["dp"], colour=BLUE)

    els = node("qc", 1280, 200, "QC Manager", w=190, h=60, colour=RED, size=14)
    n["qc"] = els[0]; e += els
    e += edge("e_t_qc", n["t"], n["qc"], "complaint", RED)

    els = node("done", 1280, 340, "Approved", w=190, h=60, colour=GREEN, size=14)
    n["done"] = els[0]; e += els
    e += edge("e_t_done", n["t"], n["done"], "quotation", GREEN)

    els = node("rej", 300, 420, "Back to raiser\n+ reason", w=220, h=70, colour=RED, size=14)
    n["rej"] = els[0]; e += els
    for a in ("dm", "sm", "rm"):
        e += edge(f"e_{a}_rej", n[a], n["rej"], "", RED, dashed=True)

    e += note("n1", 0, 260,
              "THRESHOLDS ARE DATA\n\n"
              "approval_threshold(doc_type, role,\n"
              "                   territory_id, max_amount)\n\n"
              "Global fallback row where territory is NULL.\n"
              "Seed one number now, split per state later\n"
              "with no migration.", w=350, colour=YELLOW)
    e += note("n2", 1040, 440,
              "APPROVERS NEVER UPDATE THE BUSINESS ROW.\n\n"
              "They write their own approval_step (needs the\n"
              "`approve` permission). A SECURITY DEFINER\n"
              "function then moves the document's status\n"
              "and NOTHING else.\n\n"
              "That is why `approve` is a distinct permission\n"
              "from `edit`: collapsing them would hand every\n"
              "approver a price-editing capability.\n\n"
              "Test: Account Mgr CAN approve an order and\n"
              "CANNOT change grand_total.", w=430, colour=RED)
    write("05-approval-routing", e)


def f_subsidy() -> None:
    e, n = [], {}
    e += title("Subsidy - three calculations, one pipeline",
               sub="The rounding policy is what makes one pipeline reproduce three workbooks. "
                   "It is data, not code.",
               status="BUILT (FS-008). All three workbooks reproduce to the paisa. "
                      "Applications and stages are FS-009.",
               status_colour=GREEN)

    cols = [("drip", 0, "DRIP",
             "quantities TYPED\nhead unit YES\nblocks A-G (7)\nJantri 2-D bilinear\n"
             "2 crops\nrounds EVERY block"),
            ("mini", 380, "MINI SPRINKLER",
             "quantities TYPED\nhead unit YES\nblocks A-G (7)\nJantri 2-D, own rows\n"
             "1 crop\nrounds ONE block"),
            ("spr", 760, "SPRINKLER",
             "quantities BY AREA\nhead unit NONE\nblocks A + B only\nJantri 1-D EXACT\n"
             "1 crop\nrounds all but B")]
    for eid, x, hdr, body in cols:
        els = node(eid + "_h", x, 40, hdr, w=320, h=54, colour=VIOLET, size=17)
        n[eid + "_h"] = els[0]; e += els
        els = node(eid, x, 110, body, w=320, h=180, colour=GREY, size=14)
        n[eid] = els[0]; e += els
        e += edge(f"e_{eid}", n[eid + "_h"], n[eid], colour=VIOLET)

    els = node("mast", 380, 330, "MASTERS IN FORCE on as_of\neffective_from <= d < effective_to",
               w=380, h=70, colour=YELLOW)
    n["mast"] = els[0]; e += els

    els = node("pipe", 130, 450, "COST PIPELINE\nblocks, at the cells\nthis system rounds",
               w=300, h=86, colour=BLUE)
    n["pipe"] = els[0]; e += els
    els = node("jan", 620, 450, "JANTRI unit cost\ninterpolated, or\nlooked up exactly",
               w=300, h=86, colour=BLUE)
    n["jan"] = els[0]; e += els
    e += edge("e_m_p", n["mast"], n["pipe"], colour=YELLOW)
    e += edge("e_m_j", n["mast"], n["jan"], colour=YELLOW)

    els = node("sub", 370, 600, "subsidy = MIN(cost, jantri+sump) x pct", w=400, h=64, colour=GREEN)
    n["sub"] = els[0]; e += els
    e += edge("e_p_s", n["pipe"], n["sub"], colour=GREEN)
    e += edge("e_j_s", n["jan"], n["sub"], colour=GREEN)

    els = node("cat", 370, 710, "8 categories x 2 variants\n70 / 80 / 85 / 90, and 55 / 45",
               w=400, h=70, colour=GREEN)
    n["cat"] = els[0]; e += els
    e += edge("e_s_c", n["sub"], n["cat"], colour=GREEN)

    els = node("fs", 370, 830, "FARMER SHARE\nrounded terms, then derived", w=400, h=70,
               colour=GREEN)
    n["fs"] = els[0]; e += els
    e += edge("e_c_f", n["cat"], n["fs"], colour=GREEN)

    els = node("st", 370, 950, "Applications, stages 1-17\nFS-009, not built", w=400, h=70,
               colour=VIOLET)
    n["st"] = els[0]; e += els
    e += edge("e_f_st", n["fs"], n["st"], colour=VIOLET)

    e += note("n1", 1120, 40,
              "THE WORKBOOKS ARE THE SPEC, AND THEY HAVE DEFECTS.\n\n"
              "Two inspection floors are a malformed nested IF\n"
              "that returns FALSE at exact equality. The Mini\n"
              "sump term points at an empty cell. The 2-D\n"
              "interpolation goes NEGATIVE past its largest row.\n\n"
              "Each is reproduced or diverged from deliberately.\n"
              "Every divergence carries a warning code and a gap.\n"
              "Do not 'fix' one without reading its rule first.", w=430, colour=RED)
    e += note("n2", 1120, 290,
              "ROUNDING IS PER SYSTEM AND PER CELL.\n\n"
              "Drip rounds every block. Mini rounds exactly one\n"
              "(insurance) plus two kinds of line. Sprinkler\n"
              "rounds every block but the inspection.\n\n"
              "Five booleans could not express the middle one.\n"
              "subsidy_system carries two arrays of named cells\n"
              "instead, checked against what the engine knows.", w=430, colour=RED)
    e += note("n3", 1120, 540,
              "SPACING: the larger of the STANDARD and the\n"
              "DESIGNED. The standard is the INTER-CROP's when\n"
              "the block has one, not the main crop's.\n"
              "On the client's own sample that is Rs 78,780.\n\n"
              "Outside the tabulated rows the engine CLAMPS and\n"
              "warns; the workbook extrapolates, to a negative\n"
              "unit cost at 20 m. A parameter restores the\n"
              "workbook. GAP-078, GAP-081.", w=430, colour=RED)
    e += note("n4", 1120, 800,
              "STILL THE CLIENT'S TO ANSWER (GAP-076 to 085):\n\n"
              "  an off-step Sprinkler area (refused today)\n"
              "  what the Mini sump should do\n"
              "  which category each capped row means\n"
              "  the head-unit divisor with no group\n\n"
              "Each is a named row in subsidy_parameter or a\n"
              "null column, so answering one is a data change\n"
              "and a fixture re-run, never archaeology.", w=430, colour=YELLOW)
    e += note("n5", 1120, 1020,
              "Nothing is stored. /subsidy/calculate is a preview,\n"
              "safe on every keystroke, and takes no idempotency\n"
              "key. FS-009 stores the calculation on the\n"
              "application with everything needed to reproduce it.", w=430, colour=GREY)
    write("06-subsidy", e)


def f_outbox() -> None:
    e, n = [], {}
    e += title("Message delivery", sub="Never send inside a request handler.",
               status="BUILT (FS-007): the 11za adapter, WhatsApp only. The OTP goes out on "
                      "WhatsApp (ADR-040). Delivery status and inbound are FS-007a.",
               status_colour=GREEN)

    els = node("svc", 0, 60, "Service", w=220, h=64, colour=BLUE); n["svc"] = els[0]; e += els
    els = node("tx", 300, 40, "business row\n+ activity_event\n+ outbox row\nONE TRANSACTION",
               w=260, h=110, colour=GREEN); n["tx"] = els[0]; e += els
    e += edge("e1", n["svc"], n["tx"])

    els = node("wk", 660, 60, "worker\none row per transaction\nLIMIT 1 FOR UPDATE\nSKIP LOCKED",
               w=220, h=100, colour=VIOLET)
    n["wk"] = els[0]; e += els
    e += edge("e2", n["tx"], n["wk"], colour=VIOLET)

    els = node("port", 960, 60, "MessageProvider\n(the port)", w=230, h=70, colour=YELLOW)
    n["port"] = els[0]; e += els
    e += edge("e3", n["wk"], n["port"], colour=YELLOW)

    for i, (eid, lbl, c) in enumerate([("mock", "Mock\n(default, local)", GREY),
                                       ("za", "11za\nWhatsApp\nsendTemplate", GREEN),
                                       ("sms", "SMS\nnot built (ADR-040)", GREY),
                                       ("mail", "Email\nnot built", GREY)]):
        els = node(eid, 1280, i * 92, lbl, w=180, h=70, colour=c, size=14)
        n[eid] = els[0]; e += els
        e += edge(f"e_p_{eid}", n["port"], n[eid], colour=c, dashed=(eid != "za"))

    els = node("cb", 960, 300, "status webhook (FS-007a)\nsent -> delivered -> read",
               w=280, h=76, colour=BLUE)
    n["cb"] = els[0]; e += els
    e += edge("e_cb", n["cb"], n["tx"], colour=BLUE, dashed=True)

    e += note("n1", 300, 190,
              "The outbox row is written in the SAME\n"
              "transaction as the business change.\n\n"
              "So the message exists if the change\n"
              "committed, and does NOT if it rolled back.\n"
              "That is what prevents 'the order was\n"
              "cancelled but the customer got a\n"
              "confirmation'.", w=340, colour=GREEN)
    e += note("n2", 660, 210,
              "ONE ROW PER TRANSACTION (rule 7).\n"
              "Fifty FOR UPDATE locks do not survive\n"
              "the first commit, so a batch and a\n"
              "per-row commit cannot coexist. A crash\n"
              "resends at most one message.\n\n"
              "A transient failure (timeout, 429, 5xx,\n"
              "a token error) charges NOTHING: the row\n"
              "waits a minute, and the third inside a\n"
              "window opens a shared breaker in Redis.\n"
              "Only the provider's refusal of a message\n"
              "spends one of its five attempts.\n\n"
              "Dead on claim, uncharged: too old for its\n"
              "template (OTP: ttl - 60 s, ack: 24 h), a\n"
              "newer code for the number, a withdrawn\n"
              "lead, a second ack inside a day, a channel\n"
              "with no adapter. The payload is cleared\n"
              "when a row leaves pending.", w=330, colour=VIOLET)
    e += note("n4", 300, 420,
              "THE OTP IS A WHATSAPP AUTHENTICATION\n"
              "TEMPLATE (ADR-040). The sign-in request\n"
              "is the opt-in; the screen says so.\n\n"
              "A resend supersedes the earlier code's\n"
              "row inside the definer (SKIP LOCKED, so\n"
              "it never waits behind a send: that wait\n"
              "would name registered numbers). The\n"
              "worker retires a stale row on every\n"
              "claim. Verification re-reads the\n"
              "challenge under the number's lock, or\n"
              "an older code could sign in and burn\n"
              "the newer one (reproduced in review).", w=340, colour=RED)
    e += note("n3", 1280, 400,
              "PROVIDER PORT (ADR-020)\n\n"
              "Nothing outside api/integrations/whatsapp/\n"
              "knows which provider is in use; the worker\n"
              "maps outcomes (accepted, transient, refused,\n"
              "permanent) onto rows. One HTTP client per\n"
              "worker process, a total deadline per send.\n\n"
              "11za: authToken is in the request BODY.\n"
              "The body is built inside send() and exists\n"
              "nowhere else; every error is scrubbed of\n"
              "the token and of every value sent; a\n"
              "transport exception leaves as its class\n"
              "name. sendTemplate returns NO message id\n"
              "(only IsSuccess); classify on the body.\n"
              "tags carries our row id for FS-007a.\n\n"
              "dev.py whatsapp-check: the two templates\n"
              "exist, are approved, take our values.", w=420, colour=YELLOW)
    write("07-message-delivery", e)


def f_money() -> None:
    e, n = [], {}
    e += title("Where money is decided",
               sub="Three pure functions. Two places where a bug is a legal problem.",
               status="GST ENGINE AND SUBSIDY BUILT (FS-008, FS-010). Discounts and "
                      "balances are not: no orders, no receipts.",
               status_colour=YELLOW)

    els = node("gst", 0, 60, "GST ENGINE", w=300, h=56, colour=GREEN); n["gst"] = els[0]; e += els
    e += note("gstn", 0, 130,
              "BUILT: api/domain/pricing/tax.py\n\n"
              "ROUND IN PRINT ORDER:\n"
              "  gross    = round2(rate x qty)\n"
              "  discount = round2(gross x pct/100)\n"
              "  taxable  = gross - discount\n"
              "One-shot rounding differs on 21 of 105\n"
              "inputs and prints three figures that do\n"
              "not add up.\n\n"
              "Intra-state -> CGST + SGST, EACH at half\n"
              "the slab and rounded on its own, so the\n"
              "two are always equal.\n"
              "Inter-state -> IGST at the full slab.\n\n"
              "Document total = SUM of rounded lines,\n"
              "never a recomputation. Those differ by\n"
              "paise, and paise are what an auditor\n"
              "checks.\n\n"
              "Rate comes from the item's HSN, so one\n"
              "quotation carries several rates:\n"
              "  material          5%\n"
              "  installation      5%\n"
              "  insurance        18%\n"
              "  inspection       18%\n"
              "  farmer education  0%", w=340, colour=GREEN)

    els = node("disc", 420, 60, "DISCOUNT CASCADE", w=340, h=56, colour=YELLOW)
    n["disc"] = els[0]; e += els
    e += note("discn", 420, 130,
              "THREE tiers, each on the RUNNING balance,\n"
              "then schemes as a fourth.\n\n"
              "  70.00  rate x qty\n"
              "  63.00  after 10%\n"
              "  59.85  after 5%\n"
              "  58.05  after 3%\n\n"
              "All NINE intermediate values are stored.\n"
              "A percentage edited later must never\n"
              "restate a historical order.", w=350, colour=YELLOW)

    els = node("sub", 880, 60, "SUBSIDY", w=300, h=56, colour=GREEN); n["sub"] = els[0]; e += els
    e += note("subn", 880, 130,
              "BUILT: api/domain/subsidy/\n\n"
              "Per system. Capped by Jantri.\n"
              "Eight categories.\n\n"
              "Matrix values imported at FULL precision\n"
              "and never rounded at load.\n\n"
              "THE TWO ENGINES ARE ALLOWED TO DIFFER,\n"
              "and a subsidy quotation NEVER calls\n"
              "tax.py. A pump is 18% commercially and\n"
              "5% inside a subsidy block. Both have a\n"
              "test so nobody harmonises them later.\n\n"
              "INTERPOLATE ONCE. Two chained divisions\n"
              "put 0.462 Ha at 1.45 m on 62971.2499..\n"
              "where the exact value is 62971.25, and\n"
              "the 70% share then rounded DOWN.\n\n"
              "See flow 06.", w=330, colour=GREEN)

    els = node("bal", 420, 520, "OUTSTANDING BALANCE", w=340, h=56, colour=GREEN)
    n["bal"] = els[0]; e += els
    e += note("baln", 420, 590,
              "Aggregate EACH collection separately\n"
              "BEFORE joining.\n\n"
              "Joining allocations and adjustments then\n"
              "summing multiplies both:\n\n"
              "  10,000 order\n"
              "  allocations 2,000 + 3,000\n"
              "  adjustments   100 +   200\n"
              "  naive join  -> -600     WRONG\n"
              "  CTEs        ->  4,700   right\n\n"
              "Reproduced against Postgres 16.14.\n\n"
              "Reversed receipts must be excluded, or a\n"
              "bounced cheque leaves the dealer\n"
              "looking paid.", w=400, colour=GREEN)

    e += note("rule", 0, 520,
              "MONEY RULES\n\n"
              "numeric(14,2) in the database.\n"
              "Decimal in Python, never float.\n"
              "A decimal STRING in JSON: \"1234.56\".\n\n"
              "Tests compare Decimal exactly -\n"
              "never pytest.approx. Off by a paisa\n"
              "is a failure.\n\n"
              "Every document stores its resolved\n"
              "values at creation: rate,\n"
              "price_list_item_id, discount amounts,\n"
              "subsidy result, matrix version.", w=380, colour=INK)
    write("08-money", e)


def f_pricing() -> None:
    e, n = [], {}
    e += title("Pricing a line: which rate, which tax, and what may change",
               sub="Per product, not per document. One snapshot per document. "
                   "A published rate is never corrected, only superseded.",
               status="BUILT. FS-010: /products, /tax-rates, /price-lists, "
                      "/pricing/quote-lines, migrations 010 and 011.",
               status_colour=GREEN)

    steps = [
        ("p1", "POST /pricing/quote-lines\nproduct ids, quantities, discounts,\n"
               "and WHERE THE GOODS ARE DELIVERED", BLUE),
        ("p2", "the caller's scope\npartner -> their own tier, from their own row\n"
               "no partner -> the farmer tier\na partner_id in the body is REFUSED for a partner",
         RED),
        ("p3", "the seller's registration in force\n-> its state\n"
               "ship-to territory -> up the closure -> its state", BLUE),
        ("p4", "ONE statement reads every applicable rate\n"
               "for every line, published and in force", GREEN),
        ("p5", "per product: the most specific list wins\n"
               "state+tier > STATE > tier > neither", VIOLET),
        ("p6", "tax.py: gross, discount, taxable, then the split\n"
               "same state -> CGST + SGST at half the slab each\n"
               "different state -> IGST at the full slab", GREEN),
        ("p7", "200 OK. Every printed figure, in print order.\n"
               "Nothing stored. Nothing locked.", GREEN),
    ]
    y = 60
    for eid, label, colour in steps:
        els = node(eid, 300, y, label, w=520, h=86, colour=colour)
        n[eid] = els[0]
        e += els
        y += 150
    order = [s[0] for s in steps]
    for a, b in zip(order, order[1:], strict=False):
        e += edge(f"e_{a}_{b}", n[a], n[b])

    e += note("nRed1", 880, 210,
              "THE TIER COMES FROM THE ROW, NEVER THE REQUEST\n\n"
              "A restrictive policy on price_list enforces it, not\n"
              "a permissive one. Written permissively, a staff caller\n"
              "has no partner, the comparison is NULL for every tier\n"
              "row, and STAFF RESOLVE NOTHING BUT THE BASE LIST -\n"
              "which breaks this endpoint the day a tier list exists.\n\n"
              "Permissive policies also OR together, so a later one\n"
              "would defeat the rule entirely.", w=460, colour=RED)

    e += note("nRed2", 880, 510,
              "THE PLACE OF SUPPLY IS THE SHIP-TO\n\n"
              "For goods it is where delivery ends, resolved UP to\n"
              "its state through territory_closure. Defaulting to the\n"
              "dealer's own state under-collects the inter-state tax,\n"
              "which is a credit note rather than a rounding argument.",
              w=460, colour=RED)

    e += note("nGreen1", 880, 660,
              "ONE STATEMENT, ONE SNAPSHOT\n\n"
              "A query per line takes a fresh snapshot each time, so\n"
              "a document could carry old rates on its first hundred\n"
              "lines and new ones on its last hundred while a list\n"
              "was being published underneath it.", w=460, colour=GREEN)

    e += note("nViolet1", 880, 810,
              "PER PRODUCT, NOT PER DOCUMENT\n\n"
              "So a state list holding three corrections sits OVER a\n"
              "complete base list and overrides only those three.\n"
              "Per document would refuse a forty-line quotation\n"
              "because one product is missing a rate.\n\n"
              "When a document draws from more than one list it SAYS\n"
              "SO: mixed_price_lists. Right if a state list is a\n"
              "discount layer, a mispricing if it replaces the base,\n"
              "and nobody has told us which (GAP-087).", w=460, colour=VIOLET)

    e += note("nGreen2", 0, 810,
              "WHAT THE RESPONSE CARRIES, AND WHY\n\n"
              "gross, cgst_rate and sgst_rate are RETURNED so\n"
              "nothing on the screen re-derives them and lands on\n"
              "a different paisa.\n\n"
              "intra_state is returned so the document does not\n"
              "re-derive which tax applies.\n\n"
              "price_list_item_id and gst_rate_id are returned so\n"
              "FS-005 can RE-RESOLVE AND COMPARE at save. That\n"
              "closes the preview-to-save window with no lock,\n"
              "because a published list never changes its rates\n"
              "and a published item is never deleted.", w=460, colour=GREEN)

    e += note("nYellow1", 0, 1180,
              "PUBLISHING: CLOSE FIRST, PUBLISH SECOND\n\n"
              "In one transaction. The other order RAISES the\n"
              "exclusion constraint, because for that instant two\n"
              "published lists cover the same scope and the same day.\n\n"
              "It refuses a list that does not price every active\n"
              "product, unless the caller overrides. A successor\n"
              "built over March and half filled would, on 1 April,\n"
              "leave every other product falling through or\n"
              "refusing to price.", w=460, colour=YELLOW)

    e += note("nRed3", 480, 1180,
              "WHAT THE DATABASE REFUSES, NOT THE SERVICE\n\n"
              "A published list cannot return to draft: that route\n"
              "made its rates editable again through the draft-only\n"
              "item policies.\n\n"
              "A dated master's VALUE cannot be edited in place -\n"
              "a category percentage, a parameter, a rate, a slab,\n"
              "a classification. effective_to and is_active still\n"
              "move, because closing a row IS an update.\n\n"
              "Both are triggers in migration 011. Found by a\n"
              "cross-vendor review, not by us.", w=460, colour=RED)

    e += note("nYellow2", 960, 1180,
              "STILL A STAND-IN\n\n"
              "Every price and every tax code on this box is ours,\n"
              "not the client's, and every line that uses one comes\n"
              "back with provisional_fields and a warning. SHOW IT.\n"
              "Fine for testing, not for a quotation anyone sends.\n\n"
              "The seller's registration is the default one rather\n"
              "than the supplying warehouse's, because warehouses\n"
              "do not exist yet (GAP-088).", w=460, colour=YELLOW)

    write("11-pricing", e)


def f_quotation() -> None:
    e, n = [], {}
    e += title("A quotation: saved, frozen, numbered, sent, answered",
               sub="The save re-resolves every line. The send is a database transaction and "
                   "nothing else. The worker renders. A sent document never changes.",
               status="DESIGN (FS-005 rev 2, plan review round 2 in progress). Nothing built. "
                      "Pricing underneath it is FS-010, built.",
               status_colour=RED)

    steps = [
        ("q1", "POST /quotations  on a QUALIFIED lead\nlines: product, qty, three discounts,\n"
               "and the ids the preview showed", BLUE),
        ("q2", "re-resolve every line at price_effective_date\n"
               "(FS-010: state > tier, dated tax masters)\n"
               "ids differ from the preview -> 409 rate_changed", GREEN),
        ("q3", "INSERT quotation + lines. NO NUMBER YET.\nscope columns copied from the lead\n"
               "activity_event quotation.created (carries lead_id)", BLUE),
        ("q4", "draft: PATCH header, PUT lines, re-priced on every save\n"
               "expected_status on every mutation", BLUE),
        ("q5", "POST /send: lock draft (and predecessor, lower version first)\n"
               "re-resolve and compare again -> 409 rate_changed\n"
               "predecessor accepted -> 409", YELLOW),
        ("q6", "allocate QT/GJ/2026-27/00001  (definer, row lock,\n"
               "LAST read before the write)\nvalid_until = send date IST + 45 d\n"
               "share token derived by HMAC, only its hash stored", GREEN),
        ("q7", "lead_stage_from_quotation(lead, 'quoted')\n"
               "ONE definer function moves the lead, or refuses:\n"
               "lost / merged / dormant / deleted -> 422 lead_not_open", RED),
        ("q8", "COMMIT. status sent, pdf_state pending.\n"
               "No network call happened.", GREEN),
        ("q9", "WORKER, every 5 s, as the system principal:\n"
               "claim one pending (definer, SKIP LOCKED)\n"
               "render HTML -> PDF, put to R2, mark ready,\n"
               "THEN queue the WhatsApp link", VIOLET),
        ("q10", "GET /public/q/{token}: number, total, validity.\n"
                "NO name, NO mobile, NO lines.\n"
                "GET /public/q/{token}/pdf: the view is recorded HERE,\n"
                "then 302 to a ten-minute presigned URL", BLUE),
        ("q11", "POST /transition: accepted / rejected / negotiation\n"
                "accepted -> lead WON (through the same definer)\n"
                "past valid_until (IST) -> 422 quotation_expired", GREEN),
        ("q12", "POST /revise -> version n+1, same number, new draft\n"
                "sending it sets superseded_by_id on version n\n"
                "version n keeps its status, PDF and link", BLUE),
    ]
    y = 60
    for eid, label, colour in steps:
        els = node(eid, 300, y, label, w=560, h=92, colour=colour)
        n[eid] = els[0]
        e += els
        y += 150
    order = [s[0] for s in steps]
    for a, b in zip(order, order[1:], strict=False):
        e += edge(f"e_{a}_{b}", n[a], n[b])

    e += note("nRed1", 920, 60,
              "THE LEAD IS NEVER UPDATED DIRECTLY\n\n"
              "An UPDATE on a lead the caller no longer owns\n"
              "is filtered by RLS to zero rows and raises\n"
              "nothing. The event written beside it would\n"
              "record a move that did not happen.\n\n"
              "lead_stage_from_quotation() requires\n"
              "lead_visible() and leads.edit, locks the lead,\n"
              "applies the coupling table, and returns the\n"
              "previous stage or raises. Every role that can\n"
              "create or edit a quotation holds leads.edit at\n"
              "the same scope, so it never locks out a\n"
              "legitimate caller (edge case 2, plan review B-8).",
              w=460, colour=RED)

    e += note("nRed2", 920, 420,
              "NO NETWORK CALL INSIDE THE TRANSACTION\n\n"
              "Rev 1 rendered the PDF and PUT it to R2 inside\n"
              "the send, holding two row locks and a pooled\n"
              "connection for the provider's timeout. Rev 2\n"
              "moves the render, the upload and the outbox row\n"
              "to the worker. Two things fall out for free: the\n"
              "outbox INSERT policy (narrowed to lead_ack and\n"
              "the system principal in 006) needs no new arm,\n"
              "and WeasyPrint never runs in the API process.\n\n"
              "The system principal holds no module\n"
              "permissions, so the worker touches quotations\n"
              "only through definer functions guarded on\n"
              "app_is_system().",
              w=460, colour=RED)

    e += note("nRed3", 920, 780,
              "TODAY IS today_ist(), NEVER current_date\n\n"
              "The box runs UTC. At 00:05 IST current_date is\n"
              "still yesterday, so a job written with it expires\n"
              "every quotation a day late and disagrees with\n"
              "the service for five and a half hours a night.\n"
              "The job takes the date as a parameter; the\n"
              "service and the public JSON use the same clock.",
              w=460, colour=RED)

    e += note("nGreen1", 920, 1000,
              "SCOPE MIRRORS THE LEAD\n\n"
              "owner_user_id, owner_org_unit_id and territory_id\n"
              "are the lead's, propagated by a definer trigger\n"
              "when the lead is reassigned, corrected or merged.\n"
              "The creator is created_by. The immutability\n"
              "trigger admits those three columns only at\n"
              "trigger depth 2, never from a statement.\n\n"
              "Quotation events are visible to whoever can see\n"
              "the quotation; lead_timeline() filters them.",
              w=460, colour=GREEN)

    e += note("nYellow1", 920, 1260,
              "ASSUMPTIONS WITH GAPS (103 to 119)\n\n"
              "Number at send, own series, the lead's state.\n"
              "Versioning not editing (question 2.4).\n"
              "Each discount tier rounded before the next:\n"
              "one paisa apart from the client's sheet on its\n"
              "own seven lines (GAP-118).\n"
              "Acceptance wins the lead; several accepted\n"
              "quotations per lead allowed.\n"
              "Stand-in prices sendable with a banner.\n"
              "No approval gate until the engine (W4).\n"
              "External quotation and attachments: FS-005a.",
              w=460, colour=YELLOW)

    e += note("nGrey1", 300, y + 20,
              "Not here: the sales order (W4), the approval chain, the price-list\n"
              "selector on a revision (GAP-116), export / marketing / sample /\n"
              "subsidised types, streaming the PDF through the API.",
              w=560, colour=GREY)

    write("12-quotation", e)


def f_auth() -> None:
    e, n = [], {}
    e += title("Signing in, and staying signed in",
               sub="Two doors. Four endpoints that cannot carry a token. "
                   "One rotation with a stolen-token alarm.",
               status="BUILT and tested end to end. No code is delivered yet (GAP-027).",
               status_colour=GREEN)

    for i, (eid, lbl, colour) in enumerate([
        ("staff", "STAFF\nemail + password", BLUE),
        ("portal", "DEALER / FARMER\nmobile + OTP", VIOLET),
    ]):
        els = node(eid, i * 460, 0, lbl, w=340, h=70, colour=colour)
        n[eid] = els[0]
        e += els

    steps_staff = [
        ("s1", "POST /auth/login", BLUE),
        ("s2", "auth_lookup_staff()\nlocked? hash? active?", VIOLET),
        ("s3", "argon2 verify\nALWAYS, even for an\nunknown address", GREEN),
        ("s4", "auth_create_session()\n+ activity_event", GREEN),
    ]
    steps_portal = [
        ("p1", "POST /auth/otp/request\nalways 202", VIOLET),
        ("p2", "auth_issue_otp_challenge()\ncap + row + outbox, ONE call", VIOLET),
        ("p3", "POST /auth/otp/verify\n5 attempts, then burned", VIOLET),
        ("p4", "auth_create_session()\n+ activity_event", GREEN),
    ]
    for col, steps in enumerate([steps_staff, steps_portal]):
        prev = ["staff", "portal"][col]
        for i, (eid, lbl, colour) in enumerate(steps):
            els = node(eid, col * 460, 120 + i * 110, lbl, w=340, h=80, colour=colour)
            n[eid] = els[0]
            e += els
            e += edge(f"e_{eid}", n[prev], n[eid])
            prev = eid

    els = node("bundle", 230, 580, "access JWT 15 min  +  refresh cookie 30 days",
               w=570, h=70, colour=GREEN)
    n["bundle"] = els[0]
    e += els
    e += edge("e_s4_b", n["s4"], n["bundle"], colour=GREEN)
    e += edge("e_p4_b", n["p4"], n["bundle"], colour=GREEN)

    for i, (eid, lbl, colour) in enumerate([
        ("r1", "POST /auth/refresh\nno Authorization header", YELLOW),
        ("r2", "1. replay cache?\nhit inside 90s -> the same bundle", GREEN),
        ("r3", "2. claim it\nUPDATE ... WHERE used_at IS NULL", RED),
        ("r4", "3. re-check the user\nactive? deleted? token_version?", RED),
        ("r5", "rotate: new pair, same family", GREEN),
    ]):
        els = node(eid, 230, 700 + i * 110, lbl, w=570, h=80, colour=colour)
        n[eid] = els[0]
        e += els
        if i:
            e += edge(f"e_r{i}", n[f"r{i}"], n[eid])
    e += edge("e_b_r1", n["bundle"], n["r1"])

    els = node("reuse", 900, 920, "USED ALREADY\n-> revoke the WHOLE family",
               w=320, h=80, colour=RED)
    n["reuse"] = els[0]
    e += els
    e += edge("e_r3_reuse", n["r3"], n["reuse"], "0 rows", colour=RED, dashed=True)

    e += note("nRed1", 900, 40,
              "THE FOUR THAT CARRY NO TOKEN\n\n"
              "login, otp/verify, refresh, cookie-only logout.\n"
              "They run on get_db_anon, which sets NO claim and\n"
              "holds NO table grants - they reach the database\n"
              "only through eight SECURITY DEFINER functions.\n\n"
              "app_user holds every password hash. A connection\n"
              "with no claim must not be able to read it.", w=440, colour=RED)

    e += note("nRed2", 900, 300,
              "REJECTIONS RETURN, THEY DO NOT RAISE\n\n"
              "The dependency owns the transaction. An exception\n"
              "unwinds through it and ROLLS BACK whatever the\n"
              "rejection just wrote.\n\n"
              "It shipped that way once: every failed login was\n"
              "rolled back, so the 5-failure lockout did not\n"
              "exist. Six wrong passwords, zero rows.\n\n"
              "The same shape would discard the family\n"
              "revocation - the alarm fires and revokes nothing.", w=440, colour=RED)

    e += note("nRed3", 900, 1060,
              "THE CACHE WRITE GOES BEFORE COMMIT\n\n"
              "while the claim's row lock is still held.\n"
              "That ordering IS the mechanism: an overlapping\n"
              "loser blocks on the lock and therefore always\n"
              "wakes to a written cache.\n\n"
              "Move it after COMMIT and the two-tab race\n"
              "reopens as a family revocation.", w=440, colour=RED)

    e += note("nGreen1", 0, 470,
              "One message for wrong, unknown and disabled -\n"
              "and the argon2 verify runs even when there is no\n"
              "user, against a dummy hash. Otherwise 'one\n"
              "message for both' is still an oracle, measured\n"
              "with a stopwatch.", w=400, colour=GREEN)

    e += note("nGreen2", 460, 470,
              "Always 202, identical body, known or not.\n"
              "A different answer makes this an\n"
              "'is this dealer registered' oracle, and a 429\n"
              "makes the rate limiter the same oracle.\n\n"
              "So the UI cannot tell whether a code was sent.", w=400, colour=GREEN)

    e += note("nYellow", 230, 1270,
              "WHAT IS NOT BUILT YET\n\n"
              "No provider adapter: the code reaches\n"
              "notification_outbox and stops (GAP-027). Half\n"
              "the user base signs in this way.\n\n"
              "Staff creation, the forced password change, unlock and\n"
              "sign-out-everywhere are FS-006 (canvas 10).\n\n"
              "app_anon does not exist on the dev box, so the\n"
              "containment above is documentation until the\n"
              "VPS arrives (GAP-021).", w=570, colour=YELLOW)

    write("09-authentication", e)


def f_admin() -> None:
    e, n = [], {}
    e += title("Administration: people, offices, territories, partners",
               sub="One administrator creates everyone else. Two enforcers on every write. "
                   "The database refuses the states the rules forbid.",
               status="BUILT. FS-006: /users, /auth/password, /lookups/roles, /org-units, "
                      "/territories, /partners, migration 007, the showcase seed.",
               status_colour=GREEN)

    steps = [
        ("u1", "POST /users\nstaff: email + role + open office + temp password\n"
               "partner user: mobile + active partner (role = its type)", BLUE),
        ("u2", "first sign-in with the temporary password", BLUE),
        ("u3", "get_db: must_change_password?\n-> 403 password_change_required\n"
               "except GET /auth/me and POST /auth/password", RED),
        ("u4", "POST /auth/password\nverify, then auth_set_own_password():\n"
               "compare-and-set on the verified hash, revoke after", GREEN),
        ("u5", "works leads; PATCH corrects; set-password / revoke / unlock\n"
               "each a definer guarded on users.edit + scope", BLUE),
        ("u6", "POST /users/{id}/handover\nlock both people FOR UPDATE in id order,\n"
               "then the leads, 500 a call, lead.assigned each", VIOLET),
        ("u7", "deactivate: revoke first, then the flag\nDELETE: soft, no open leads", YELLOW),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid

    trees = [
        ("t1", "OFFICES  /org-units\ncreate, rename, move (closure rebuilt),\n"
               "close, reopen", BLUE),
        ("t2", "org_unit_close_guard(): active people anchored -> 23514\n"
               "the cascade's office arm deactivates nobody now", RED),
        ("t3", "TERRITORIES  /territories\nstate > district > taluka > village,\n"
               "unique names per parent, codes per level", BLUE),
        ("t4", "territory_code_guard(): a numbered state's code\n"
               "is immutable (keyed on inquiry_counter)", RED),
        ("t5", "PARTNERS  /partners\nscoped by the partners ScopeSpec;\n"
               "a dealer edits contact details only", BLUE),
        ("t6", "channel_partner_guarded_columns(): credit, terms,\n"
               "tier, type, active, deleted refused for a partner caller;\n"
               "retype refused while users are anchored", RED),
        ("t7", "close a partner: the cascade signs its users out\n"
               "reopen restores the row only (users_inactive)", YELLOW),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(trees):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid], dashed=True)
        prev = eid

    e += note("nRed1", 1240, 0,
              "THE ADMINISTRATOR FLOOR\n\n"
              "A deferred CONSTRAINT TRIGGER counts active users\n"
              "whose role holds users.edit, under one advisory\n"
              "lock, whenever an administrator's row changes.\n\n"
              "At COMMIT a raise is a 500. So every service path\n"
              "runs SET CONSTRAINTS ... IMMEDIATE before returning\n"
              "and answers 422. It then stays immediate for the\n"
              "rest of the transaction (executed).", w=420, colour=RED)
    e += note("nRed2", 1240, 300,
              "THE PRINCIPAL IS NOT A PERSON\n\n"
              "Never listed, never administered, never signed in.\n"
              "The trigger refuses a hash, a flag or a role on its\n"
              "row; auth_lookup_staff excludes it by id even with a\n"
              "hash forced in as the owner.", w=420, colour=RED)
    e += note("nRed3", 1240, 520,
              "LOCK ORDER, ALWAYS\n\n"
              "family locks (id order) > session rows > app_user\n"
              "app_user before lead; both people before any lead.\n"
              "A create into a closing anchor shares the anchor row.\n"
              "Every locking read inside a trigger is a DEFINER:\n"
              "as INVOKER it silently reads nothing.", w=420, colour=RED)
    e += note("nGreen1", 1240, 760,
              "A credential is bound to what was verified:\n"
              "auth_create_session(..., p_token_version) mints\n"
              "nothing if the version moved (ISS-077), and the\n"
              "own-password change is a compare-and-set on the\n"
              "hash it verified (409 password_changed_meanwhile).", w=420, colour=GREEN)
    e += note("nYellow1", 0, 880,
              "NOT DONE, ON PURPOSE\n\n"
              "No invitation email: the admin passes a temporary\n"
              "password out of band (GAP-064).\n"
              "A dealer does not create its own users (GAP-062).\n"
              "Reopening a partner restores no people (GAP-069).\n"
              "Regional manager / state co-ordinator cannot own a\n"
              "lead until the matrix says so (GAP-071).", w=520, colour=YELLOW)
    e += note("nViolet1", 620, 880,
              "THE SHOWCASE SEED  scripts/seed_showcase.py\n\n"
              "0 owner: sweep test leftovers older than an hour\n"
              "1 API: Gujarat's districts, talukas, villages, the offices\n"
              "2 API: one of every role, ten partners with a user;\n"
              "   every staff member completes the forced change\n"
              "3 API: ~70 leads as field officers and two dealers (OTP\n"
              "   read from the outbox: nothing sends it, GAP-027)\n"
              "4 owner: backdate over 45 days, clamped to the FY,\n"
              "   audit triggers off for one transaction", w=520, colour=VIOLET)
    write("10-administration", e)


if __name__ == "__main__":
    print("generating flows:")
    f_system(); f_request(); f_permissions(); f_lead()
    f_approval(); f_subsidy(); f_outbox(); f_money(); f_pricing()
    f_quotation(); f_auth(); f_admin()
    print(f"\nwrote to {OUT}")
