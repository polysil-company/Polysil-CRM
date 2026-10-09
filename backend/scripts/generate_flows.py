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
    e += note("sc6", 0, 1140,
              "DEALERS BY AREA  (FS-020, ADR-043, 2 Oct)\n\n"
              "A partner has no office column, so staff reach it\n"
              "through their offices' territories:\n"
              "  READ   at, under or ABOVE those territories\n"
              "         (a taluka officer sees the district dealer\n"
              "          and the state distributor)\n"
              "  WRITE  at or under only\n"
              "         (a district office cannot edit a state distributor)\n\n"
              "Safety net: a dealer on a lead, quotation or order you\n"
              "can see prices and writes onto a quotation or order,\n"
              "via partner_on_visible_document(). Tier and name only.\n"
              "Credit terms only with partners.edit.",
              w=560, colour=GREEN)
    e += note("sc7", 620, 1140,
              "TRAP: two functions PASTE the partners guard:\n"
              "  minutes_visible()  channel_partner_user_counts()\n"
              "Change the partners ScopeSpec and both must be\n"
              "re-pasted in the same migration (028 did).\n"
              "test_migration_028 fails on a stale copy.\n\n"
              "Before 2 Oct the rule was an exact territory match:\n"
              "a field officer saw no dealer at all, and could not\n"
              "quote a dealer lead (ISS-109, found in the demo).",
              w=460, colour=RED)
    write("03-permissions", e)


def f_lead() -> None:
    e, n = [], {}
    e += title("Lead capture", sub="Every source ends in create_lead(). The public one proves the "
                                   "mobile first.",
               status="BUILT. FS-003: manual entry. FS-003a: the public enquiry form and QR codes. "
                      "Inbound WhatsApp later.",
               status_colour=GREEN)

    steps = [
        ("p1", "Farmer opens /enquiry, or scans a QR code (/enquiry?qr=CODE)\n"
               "GET /public/lead-form: states, systems, types, the QR label", GREY),
        ("p2", "POST /public/leads/verify {mobile}\n"
               "lead_intake_issue() as app_anon: rate limits, the hourly ceiling,\n"
               "code hashed, outbox lead.verify -> WhatsApp code. Always 202", YELLOW),
        ("p3", "POST /public/leads {mobile, code, name, territory, ...}\n"
               "body validated BEFORE the code is touched", BLUE),
        ("p4", "intake_session(): as app_anon, lead_intake_consume()\n"
               "wrong code -> count the attempt, burn at five, 422 invalid_code", RED),
        ("p5", "code matched -> claim = the intake account, enter app_role\n"
               "same mobile already enquired today -> 200 created:false, same number", BLUE),
        ("p6", "create_lead(intake=True): the territory's unit and auto-owner,\n"
               "or unassigned; a QR code's dealer becomes the assigned partner", GREEN),
        ("p7", "LEAD + lead.created event + acknowledgement on the outbox\n"
               "returns {inquiry_no, created} and nothing else", GREEN),
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

    els = node("man", 0, 810, "Manual entry\n(CRM / dealer portal)", w=220, h=70, colour=GREY,
               size=14)
    n["man"] = els[0]
    e += els
    e += edge("e_man", n["man"], n["p6"], colour=GREY, dashed=True)

    e += note("nRed1", 920, 60,
              "A WRONG CODE MUST COMMIT ITS COUNT\n\n"
              "lead_intake_consume() returns a result, never\n"
              "raises. submit() raises the refusal AFTER the\n"
              "intake session has closed. Raise inside it and\n"
              "the attempt count rolls back: unlimited guesses.",
              w=460, colour=RED)
    e += note("nRed2", 920, 300,
              "THE INTAKE ACCOUNT SEES EVERY LEAD\n\n"
              "\"Website and QR\": leads view/create/edit and\n"
              "partners view, global. Its claim exists only\n"
              "inside POST /public/leads, after the code matched,\n"
              "and the route returns only the inquiry number.\n"
              "No password, no mobile: a trigger refuses both.",
              w=460, colour=RED)
    e += note("nGreen1", 920, 560,
              "DUPLICATES ARE FLAGGED, NEVER BLOCKED\n\n"
              "The same farmer twice on different days is two\n"
              "leads, flagged for a human. A retry the same day\n"
              "is the first lead's number back.",
              w=460, colour=GREEN)
    e += note("nYellow1", 920, 760,
              "OUR RULES, WITH GAPS\n\n"
              "300 codes an hour across the site (GAP-136).\n"
              "One public lead per mobile per day (GAP-137).\n"
              "The code rides the approved polysil_auth_otp.\n"
              "An unknown or closed QR code: a plain website lead.",
              w=460, colour=YELLOW)
    e += note("nGrey1", 300, y + 20,
              "Not here: inbound WhatsApp as a source (GAP-337, question 3a.1),\n"
              "dealership enquiries (GAP-135). Editing a QR code: canvas 46.",
              w=560, colour=GREY)
    write("04-lead-capture", e)


def f_approval() -> None:
    e, n = [], {}
    e += title("Approval routing", sub="One engine, thresholds as data. Orders are its first "
                                       "document type.",
               status="BUILT for orders (FS-011) and quotation discounts (FS-013, migration "
                      "017). Complaints (W5) are the next document type.",
               status_colour=GREEN)

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

    els = node("qc", 1280, 200, "QC Manager\n(W5, not built)", w=190, h=60, colour=GREY, size=14)
    n["qc"] = els[0]; e += els
    e += edge("e_t_qc", n["t"], n["qc"], "complaint", GREY, dashed=True)

    els = node("done", 1280, 340, "Approved\n(GAP-105, not built)", w=190, h=60, colour=GREY,
               size=14)
    n["done"] = els[0]; e += els
    e += edge("e_t_done", n["t"], n["done"], "quotation", GREY, dashed=True)

    els = node("rej", 300, 420, "Back to raiser\n+ reason", w=220, h=70, colour=RED, size=14)
    n["rej"] = els[0]; e += els
    for a in ("dm", "sm", "rm"):
        e += edge(f"e_{a}_rej", n[a], n["rej"], "", RED, dashed=True)

    e += note("n1", 0, 260,
              "THRESHOLDS ARE DATA\n\n"
              "approval_threshold(doc_type, role,\n"
              "                   territory_id, max_amount)\n\n"
              "Global fallback row where territory is NULL;\n"
              "the nearest territory row wins.\n"
              "Stand-ins: DM 1,00,000, SM 5,00,000, RM uncapped\n"
              "(question 15.1). Compared with the total\n"
              "INCLUDING GST. Fixed at submit.", w=350, colour=YELLOW)
    e += note("n3", 0, 480,
              "WHO DECIDES A STEP\n\n"
              "Levels at or below the OWNER's line level are\n"
              "dropped: an FO's order starts at DM, a DM's\n"
              "own order goes straight to Accounts.\n"
              "A higher line manager may decide a lower line\n"
              "step (absence, question 15.9). Accounts and\n"
              "Dispatch never decide a line step.\n"
              "Nobody decides an order they own, created or\n"
              "submitted. Steps decide in sequence.\n"
              "A reject returns the order to DRAFT; resubmit\n"
              "runs the whole chain again.", w=350, colour=GREEN)
    e += note("n2", 1040, 440,
              "APPROVERS NEVER UPDATE THE BUSINESS ROW.\n\n"
              "They write their own approval_step (needs the\n"
              "`approve` permission). A SECURITY DEFINER\n"
              "function then moves the document's status\n"
              "and NOTHING else.\n\n"
              "That is why `approve` is a distinct permission\n"
              "from `edit`: collapsing them would hand every\n"
              "approver a price-editing capability.\n\n"
              "Tested: Accounts CAN decide an order and\n"
              "CANNOT create or edit one (RLS-8). app_role\n"
              "has no column grant on status at all.", w=430, colour=RED)
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
               status="BUILT and LIVE on the client's 11za account since 23 Sep (FS-007, FS-012). "
                      "Delivery status and inbound are FS-007a.",
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
              "dev.py whatsapp-check: the configured\n"
              "templates exist, are approved, take our values.", w=420, colour=YELLOW)
    e += note("n5", 1280, 820,
              "WHICH TEMPLATE SENDS WHAT\n\n"
              "polysil_auth_otp     sign-in code, and the public\n"
              "                     form's code (lead.verify)\n"
              "polysil_lead_ack     the enquiry acknowledgement\n"
              "polysil_quotation    the quotation link (off on\n"
              "                     staging until R2)\n"
              "polysil_order_confirmed / _approval_waiting /\n"
              "_order_decided       the order messages (FS-012):\n"
              "                     NOT YET CREATED in 11za\n\n"
              "The order keys take their name from\n"
              "message_template, copied into the payload as\n"
              "_template. An off row writes nothing, so a\n"
              "template waiting on Meta never dead-letters.\n"
              "sync_message_templates.py turns a row on only\n"
              "when 11za lists it approved; the deploy runs it.",
              w=420, colour=YELLOW)
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
               status="BUILT (FS-005 rev 4): migration 012, /quotations, /public/q, the worker "
                      "render lease and the nightly expiry. The PDF renders in CI and the "
                      "container; not on the Windows box.",
               status_colour=GREEN)

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
               "predecessor accepted -> 409\n"
               "discount above the owner's limit, not approved\n"
               "-> 409 discount_approval_required (quotation_send_gate)", YELLOW),
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

    e += note("nDisc", -420, 700,
              "DISCOUNT APPROVAL (FS-013)\n\n"
              "Above the owner's limit: POST /request-approval.\n"
              "One step: the lowest of DM, SM, RM, Admin-Sales\n"
              "above the owner whose limit covers it.\n"
              "The request holds a HASH of the priced figures.\n"
              "An edit cancels a pending request; an edit after\n"
              "approval voids it; the decision refuses\n"
              "figures_changed. The status never moves.\n"
              "Stand-in limits 5 / 10 / 15 / 20 % (GAP-105).",
              w=380, colour=YELLOW)
    write("12-quotation", e)


def f_order() -> None:
    e, n = [], {}
    e += title("A sales order: priced, numbered, approved, dispatched",
               sub="Every mutation locks the order row first. The database moves the status; "
                   "the API never writes it.",
               status="BUILT (FS-011 rev 3.2, FS-012): migrations 013 and 016. Commercial and "
                      "industrial only. Messages wait on their 11za templates.",
               status_colour=GREEN)

    steps = [
        ("o1", "POST /orders  from ACCEPTED quotations, or lines typed in\n"
               "one lead: the lead and its farmer\n"
               "several leads of ONE dealer: no lead, the dealer is the party", BLUE),
        ("o2", "price_document(): rates at the price date,\n"
               "HSN, slab and seller registration at TODAY (IST)\n"
               "stale preview id -> 409 rate_changed", GREEN),
        ("o3", "INSERT draft + lines. NO NUMBER YET.\n"
               "order_quotations_claim(): quotations locked in id order,\n"
               "one live order each -> 409 quotation_on_order", BLUE),
        ("o4", "draft: PATCH header, PUT lines, re-priced on every save\n"
               "expected_status on every mutation", BLUE),
        ("o5", "POST /submit -> order_submit():\n"
               "zero total -> 422; nobody for a functional step -> 422 no_approver\n"
               "number SO/<state>/<FY>/<nnnnn>, chain built from the owner", YELLOW),
        ("o6", "POST /approvals/steps/{id}/decision -> record_decision()\n"
               "each open step: approval.waiting to who may decide it\n"
               "reject -> DRAFT with the reason; order.decided to the owner", GREEN),
        ("o7", "last step approves -> status approved\n"
               "order.confirmed to the buyer, order.decided to the owner,\n"
               "pdf_state = pending; the worker renders the PDF once", GREEN),
        ("o8", "POST /orders/{id}/dispatches -> dispatch_record()\n"
               "order, then its lines; never above the open quantity,\n"
               "in the line's unit precision; status derived from the lines", BLUE),
        ("o9", "void a dispatch, or close the balance short\n"
               "qty_short written only by a depth-2 trigger", BLUE),
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
              "app_role CANNOT WRITE THE STATUS\n\n"
              "sales_order grants INSERT and UPDATE on the\n"
              "draft-editable columns only. A direct UPDATE of\n"
              "status, or an INSERT naming it, is 42501 before\n"
              "any trigger runs. The trigger is the second belt:\n"
              "a new order is a fresh draft whoever inserts it.\n\n"
              "has_table_privilege() does not see column\n"
              "grants; the grant test parses them itself.",
              w=460, colour=RED)

    e += note("nRed2", 920, 380,
              "THE LOCK ORDER\n\n"
              "order -> request -> steps -> lines ->\n"
              "quotations (id order) -> counters.\n"
              "No order path locks a lead. A quotation's scope\n"
              "trigger takes the lead then quotation rows, so\n"
              "the two meet only on quotation rows.\n\n"
              "Proved for PATCH, PUT, submit, decision, cancel\n"
              "and dispatch: hold the order, wait for pg_locks\n"
              "to show the call blocked, then lock the rest.",
              w=460, colour=RED)

    e += note("nRed3", 920, 720,
              "REMARKS NEVER REACH A DEALER\n\n"
              "The remark lives on approval_step only, never in\n"
              "an event payload. A portal caller gets seq, role,\n"
              "decision and time; last_rejection.remark is the\n"
              "stock text (question 15.14).",
              w=460, colour=RED)

    e += note("nGreen1", 920, 940,
              "ONE OUTCOME PER RACE\n\n"
              "Two claims of one quotation: one order.\n"
              "Two dispatches of one line: never over-shipped.\n"
              "A decision losing to a cancel: 409 request_closed,\n"
              "never an approved cancelled order.",
              w=460, colour=GREEN)

    e += note("nYellow1", 920, 1160,
              "ASSUMPTIONS WITH GAPS (121 to 133)\n\n"
              "Thresholds are stand-ins. Tax at the submit date.\n"
              "No change after approval; cancel before dispatch.\n"
              "Short supply stays open until closed short.\n"
              "Invoice numbers recorded, not issued.\n"
              "A direct order does not move its lead.\n"
              "No stock check. Our number format.",
              w=460, colour=YELLOW)
    e += note("nYellow3", 920, 1400,
              "CREDIT LIMIT AT SUBMIT (FS-027, 047)\n\n"
              "Setting dealer_credit_check: off | warn | block.\n"
              "order_submit -> order_credit_check after the status\n"
              "UPDATE, so benefits are counted. Exposure = owed on\n"
              "payable orders less live receipts. Lock: order,\n"
              "counter, then dealer FOR NO KEY UPDATE.\n"
              "Block: 409, no figures. Warn: over_credit_limit for\n"
              "approvers only (GAP-240 to 244).",
              w=460, colour=YELLOW)

    e += note("nYellow2", -420, 900,
              "ORDER MESSAGES (FS-012)\n\n"
              "Written by the approval definers, in the\n"
              "decision's transaction. message_template is the\n"
              "one switch: an off key writes nothing, so nothing\n"
              "dead-letters while 11za approves a template.\n"
              "One alert per person per step per hour (GAP-138).\n"
              "A stalled step messages nobody (GAP-139).",
              w=380, colour=YELLOW)
    e += note("nRed4", -420, 1180,
              "THE PDF IS THE APPROVED ORDER\n\n"
              "Claim, render, upload, close: each outside the\n"
              "others' transactions, the quotation's lease.\n"
              "A cancelled order is not rendered; its link\n"
              "answers 409 order_cancelled. No approver names\n"
              "and no remarks on the page.",
              w=380, colour=RED)
    e += note("nGrey1", 300, y + 20,
              "Not here: payments, stock, schemes, export / sample / marketing /\n"
              "subsidised / replacement orders (GAP-121).",
              w=560, colour=GREY)

    write("13-order", e)


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


def f_tasks() -> None:
    e, n = [], {}
    e += title("Tasks, the planner, meetings and minutes",
               sub="Staff only. A task is for one person, given by one person, about at most one "
                   "lead, dealer or order. Minutes' action items are tasks.",
               status="BUILT. FS-014: /tasks, /planner, /planner/team, /minutes, "
                      "/lookups/meeting-types, migration 018.",
               status_colour=GREEN)

    steps = [
        ("k1", "POST /tasks\ncall, visit, meeting, follow-up, other\n"
               "a date alone = 18:00 IST; naive times refused", BLUE),
        ("k2", "assignee: yourself, or authz_user_assignable('tasks')\n"
               "an officer: only themselves -> 422 not_assignable", VIOLET),
        ("k3", "task_link_visible_as(assignee, link)\nthe claim swapped for one check, "
               "then restored\n-> 422 link_not_visible_to_assignee", RED),
        ("k4", "open: in the planner by IST day\noverdue = open and due before the day, "
               "90 days back", BLUE),
        ("k5", "complete (outcome) / cancel (reason)\nrow FOR UPDATE; the loser gets "
               "409 task_not_open", GREEN),
        ("k6", "reopen: assignee or assigner, 7 days,\nassignee still active", YELLOW),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid

    side = [
        ("m1", "POST /minutes on a lead or a dealer\nheld_at, attendees, notes, action items", BLUE),
        ("m2", "each action item: the same checks as a create\n"
               "one bad item -> 422 with fields.action_items[i],\nnothing saved", RED),
        ("m3", "task_id given: must be on the same lead or dealer;\n"
               "open -> completed as 'Minutes recorded'", GREEN),
        ("m4", "people leave: handover moves all open tasks\n(user_tasks_handover, task.reassigned "
               "each);\ndeactivate and delete refuse with open tasks", VIOLET),
        ("m5", "office move: trigger on app_user.org_unit_id\nopen tasks follow the person", GREEN),
        ("m6", "lead merge: tasks and minutes move to the survivor", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(side):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid], dashed=True)
        prev = eid

    e += note("nRed1", 1240, 0,
              "DEALERS SEE NONE OF THIS\n\n"
              "Portal roles hold no tasks permission. Minutes read\n"
              "through minutes_visible(), staff only. The lead\n"
              "timeline filters task and minutes events by the\n"
              "row's own visibility, so a dealer reading its own\n"
              "lead sees no task.* or minutes.* event.", w=420, colour=RED)
    e += note("nRed2", 1240, 260,
              "A BARE DATE IS NOT A DATETIME\n\n"
              "Pydantic reads \"2026-10-02\" as a naive midnight\n"
              "datetime. DueAt parses a 10-character string as a\n"
              "date first, so the 18:00 IST default applies.", w=420, colour=RED)
    e += note("nGreen1", 1240, 480,
              "owner_org_unit_id follows the assignee on every\n"
              "reassign, handover and office move. The manager\n"
              "above sees it; the old office stops seeing it.", w=420, colour=GREEN)
    e += note("nYellow1", 0, 760,
              "STAND-INS AND GAPS\n\n"
              "18:00, 7 days, 90 days are stand-ins (GAP-143).\n"
              "No dealer tasks (GAP-141). A drifted link shows\n"
              "hidden (GAP-142). No message on assignment\n"
              "(GAP-144). Open tasks stay open when the lead\n"
              "closes (GAP-145).", w=520, colour=YELLOW)
    write("14-tasks-and-planner", e)


def f_bell_and_messages() -> None:
    e, n = [], {}
    e += title("The bell and staff messages",
               sub="In-app notifications from the event log (FS-018) and one-to-one staff "
                   "conversations with a lead link (FS-019).",
               status="BUILT. /notifications, /conversations, /staff-directory; "
                      "migrations 023 and 024.",
               status_colour=GREEN)
    steps = [
        ("b1", "any write: API, worker or a definer\nactivity_event row, same transaction", BLUE),
        ("b2", "trigger notify_from_event (023), filtered by kind\n"
               "assigned, a note, waiting for you, decided for you", VIOLET),
        ("b3", "who may decide: approval_refusal() / complaint_refusal()\n"
               "asked as each candidate, the claim swapped and restored", VIOLET),
        ("b4", "notification rows: recipient only, read_at the only write\n"
               "GET /notifications; POST /notifications/read", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid
    side = [
        ("m1", "GET /staff-directory -> POST /conversations\nfind or open the pair (user_a < user_b)", BLUE),
        ("m2", "POST /conversations/{id}/messages\nbody 1-2000, a lead the sender can see", BLUE),
        ("m3", "message_stamp(): under the conversation's row lock\n"
               "created_at strictly increasing; the sender's own mark", VIOLET),
        ("m4", "POST /read {up_to}: up to what the screen showed\n"
               "unread = their messages after my mark", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(side):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid
    e += note("nRed1", 1240, 0,
              "A NOTIFICATION FAULT NEVER BLOCKS THE WRITE\n\n"
              "The trigger's body sits in one exception block. A fault\n"
              "is logged in notification_failure with a warning.\n"
              "An outage, a cancel, a deadlock or class XX still\n"
              "fails the write.", w=420, colour=RED)
    e += note("nRed2", 1240, 260,
              "A DEALER IS NEVER TOLD WHO DECIDED\n\n"
              "Titles never name the decider; the actor is dropped at\n"
              "write time for a partner recipient. A reject does not\n"
              "notify the next step's role.\n\n"
              "A decided or ended request clears everyone's 'waits for\n"
              "your approval' on the document first (029, ISS-108).", w=420, colour=RED)
    e += note("nRed3", 1240, 520,
              "MARK READ UP TO A MESSAGE, NEVER 'NOW'\n\n"
              "A message committing while the reader marks read would\n"
              "otherwise be counted read unseen. No UPDATE grant on\n"
              "conversation: one side cannot reset the other's mark.", w=420, colour=RED)
    e += note("nYellow1", 1240, 780,
              "Not yet: push, groups, attachments, a bell for a new\n"
              "message, retention (GAP-160 to GAP-168).", w=420, colour=YELLOW)
    write("16-bell-and-messages", e)


def f_complaints() -> None:
    e, n = [], {}
    e += title("Complaints: entry, the manager check, the quality check",
               sub="A dealer, an officer or support raises it; a manager checks it; QC gives a "
                   "verdict and chooses the remedy (FS-015b).",
               status="BUILT. FS-015 and FS-015b: /complaints, /remedy, /complaint-sla-policies, "
                      "/lookups/complaint-types, migrations 019 and 026.",
               status_colour=GREEN)

    steps = [
        ("c1", "POST /complaints (draft)\nproducts: supplied and defective\n"
               "challan and supply date optional until submit", BLUE),
        ("c2", "POST /attachments: sniffed by content, 10 MB, 10 files\n"
               "stored before the row, outside any lock (ADR-041)", VIOLET),
        ("c3", "POST /submit -> complaint_submit()\nfirst time: Poly/Comp./FY/GJ/01 and the targets\n"
               "422 missing_for_submit / nothing_defective / no_checker", BLUE),
        ("c4", "POST /check -> complaint_check()\napprove: under_qc (severity, owner)\n"
               "return: draft, the remark to the raiser", GREEN),
        ("c5", "POST /qc -> complaint_qc()\napproved or rejected, with sample and test dates\n"
               "resolved_at set", GREEN),
        ("c6", "POST /remedy (QC): refund, replacement or none\n"
               "refund: managers by amount, then Accounts pays\n"
               "replacement: a free order, Dispatch approves, ships", GREEN),
        ("c7", "closed: refund paid, replacement shipped, or none.\n"
               "A refused or withdrawn remedy returns it\nto qc_approved", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid

    side = [
        ("r1", "complaint_refusal(id, action): the one rule\nfor the definers, `can` and ?awaiting=me", VIOLET),
        ("r2", "manager check: a line role above the owner's\nline level (approval_owner_level), not raiser or owner;\n"
               "at the top, another top-level manager", BLUE),
        ("r3", "QC: a functional role with complaints.approve\n(the QC Manager), not raiser or owner", BLUE),
        ("r4", "targets: working hours Mon-Sat 09:30-18:30 IST,\nthe policy of the first submit's date;\n"
               "breached = met late, or past and unmet", YELLOW),
        ("r5", "messages: complaint.registered / .updated\nseeded off until 11za approves the templates", YELLOW),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(side):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid], dashed=True)
        prev = eid

    e += note("nRed1", 1240, 0,
              "A DEALER NEVER SEES WHO DECIDED\n\n"
              "Each decision's remark reaches the dealer (they must\n"
              "know why it came back). The decider is null on the\n"
              "complaint and the timeline, people_names never names\n"
              "them to a partner, and the internal note lives in its\n"
              "own table whose policy refuses a partner claim.", w=420, colour=RED)
    e += note("nRed2", 1240, 260,
              "THE SIZE CAP SITS INSIDE request_context\n\n"
              "FastAPI reads the whole form before any handler, so\n"
              "the cap is ASGI middleware. Outside the app's\n"
              "BaseHTTPMiddleware its exception came back as a 400\n"
              "(executed). It is registered first, so it is innermost.", w=420, colour=RED)
    e += note("nRed3", 1240, 520,
              "THE FILE LINK IS JSON, NOT A REDIRECT\n\n"
              "The app sends a bearer token; an <img> cannot.\n"
              "GET .../attachments/{id} answers {url, expires_at}.\n"
              "No storage (staging today): 503, nothing kept.", w=420, colour=RED)
    e += note("nRed4", 1240, 1040,
              "THE ORDER FIRST, THEN THE COMPLAINT\n\n"
              "Every path touching a replacement order and its\n"
              "complaint locks the order first: dispatch, cancel,\n"
              "close short, the decision, and QC's withdraw. The other\n"
              "order would deadlock QC against Dispatch (delta B-8).", w=420, colour=RED)
    e += note("nYellow2", 1240, 1300,
              "Stand-ins: refund limits 25,000 / 1,00,000 / any;\n"
              "Dispatch alone approves a replacement; QC chooses;\n"
              "closing is automatic (GAP-179 to GAP-187).", w=420, colour=YELLOW)
    e += note("nRed5", 1240, 1500,
              "A RUN OF HOLIDAYS MUST END THE SCAN (FS-028, 048)\n\n"
              "Working hours skip holidays like Sundays, read once for\n"
              "400 days; past that, 22023, never a loop to the\n"
              "statement timeout. The Python twin has the same bound.", w=420, colour=RED)
    e += note("nYellow3", 1240, 1720,
              "ESCALATION (FS-028): worker every 5 min as System.\n"
              "One bell per missed due time: owner, the check's\n"
              "manager, and the checkers or QC at that stage.\n"
              "Setting complaint_escalation off | bell (GAP-245 to 249).", w=420, colour=YELLOW)
    e += note("nGreen1", 1240, 780,
              "Both enforcers agree: status, the number and the\n"
              "targets have no UPDATE grant; only the definers\n"
              "write them. A submitted complaint's lines are frozen\n"
              "by a trigger as well as by the service.", w=420, colour=GREEN)
    write("15-complaints", e)


def f_subsidy_applications() -> None:
    e, n = [], {}
    e += title("Subsidy applications: from a won lead to the last payment",
               sub="A subsidised lead is forwarded; GGRC stages 4 to 17 are recorded as they "
                   "happen; the application closes itself on the last payment.",
               status="BUILT. FS-009: /subsidy-applications, /subsidy-stages, "
                      "/subsidy-document-types, migration 025.",
               status_colour=GREEN)
    steps = [
        ("s1", "a subsidised lead: qualified, quoted, negotiation or won\n"
               "drip, mini sprinkler or sprinkler", BLUE),
        ("s2", "POST /subsidy-applications {lead, category, calculation}\n"
               "the engine runs again; the calculation is stored, never recomputed", VIOLET),
        ("s3", "subsidy_application_create(): locks the lead\n"
               "SA/GJ/2026-27/00001, stage 4 today, the lead moves to won", GREEN),
        ("s4", "POST /{id}/stages {stage, date, values}\n"
               "any stage; back or same needs a remark; no future date", BLUE),
        ("s5", "stage 16: the amounts cleared\nstage 17: the date each one arrived", BLUE),
        ("s6", "full_fp_received: every amount above 0\nhas its date (rule 7)", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid
    side = [
        ("d1", "GET /subsidy-stages: the stages and their fields\n"
               "are data (subsidy_stage_def / _field), not code", YELLOW),
        ("d2", "POST /{id}/documents: 20-item checklist, none required\n"
               "sniffed, 10 MB, 40 files, stored before the row", VIOLET),
        ("d3", "GET /{id}/pims.xlsx: one row per line\n"
               "education CR 01, installation BQ 01, head, field", BLUE),
        ("d4", "POST /{id}/cancel {reason}\nthe lead can be forwarded again", GREY),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(side):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid], dashed=True)
        prev = eid
    e += note("nRed1", 1240, 0,
              "THE STATE CO-ORDINATOR HAS NO leads.edit\n\n"
              "It forwards leads in its state. The definer locks the\n"
              "lead itself and reads the state code itself:\n"
              "lead_state_code() gates on leads.create and refused\n"
              "the co-ordinator (found by the tests).", w=420, colour=RED)
    e += note("nRed2", 1240, 260,
              "CLOSURE READS THE LATEST VALUE PER FIELD\n\n"
              "Across every entry, newest first. Null clears a field:\n"
              "a stage-16 amount cleared back out is owed no date.\n"
              "total_fp_amt has no pair and never blocks closure.", w=420, colour=RED)
    e += note("nRed3", 1240, 520,
              "A VIEWER'S UPLOAD NEVER REACHES STORAGE\n\n"
              "The route gate is subsidy.view. The service checks\n"
              "create-or-edit before the put, then the lock re-checks.", w=420, colour=RED)
    e += note("nYellow1", 1240, 780,
              "Not yet: the printed GGRC documents (FS-009a, needs R2),\n"
              "admin edits to stages and the checklist, required\n"
              "documents, dealer applications (GAP-170 to GAP-178).", w=420, colour=YELLOW)
    write("17-subsidy-applications", e)


def f_field_tracking() -> None:
    e, n = [], {}
    e += title("Field tracking: duty, background points, visits, the map",
               sub="The Android app records while on duty and uploads in batches; managers "
                   "read their team's map and routes (FS-021, ADR-044).",
               status="BUILT (backend). /me/tracking-config, /tracking/*, /locations/batch, "
                      "/visits; migration 030. The app is the frontend track's.",
               status_colour=GREEN)
    steps = [
        ("t1", "GET /me/tracking-config\nfilters, hours, consent version, open duty", BLUE),
        ("t2", "POST /tracking/consent (current version)\nwithdraw: ends the open duty", BLUE),
        ("t3", "POST /tracking/duty/start {id from the phone}\n200 + the open one if already on duty", BLUE),
        ("t4", "POST /locations/batch {sent_at, points}\nown ids = duplicates; skew corrected; reasons named", VIOLET),
        ("t5", "location_point + tracking_latest (forward only)\nduty.last_point_at; answer carries the duty state", GREEN),
        ("t6", "POST /tracking/duty/end, or the worker:\nidle 30 min after hours, or 14 h; end = last point", BLUE),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, 0, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid
    side = [
        ("v1", "POST /visits: a lead, a dealer or a place\nno duty needed; one open visit per person", BLUE),
        ("v2", "POST /visits/{id}/photos (up to 3, 24 h)\nPOST /visits/{id}/check-out {outcome}", BLUE),
        ("v3", "GET /tracking/team/latest\nGET /tracking/users/{id}/route?date=", VIOLET),
        ("v4", "tracking_view_log: every look at someone else\nread by admin and MD only", GREEN),
    ]
    prev = None
    for i, (eid, lbl, colour) in enumerate(side):
        els = node(eid, 620, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid
    e += note("nRed1", 1240, 0,
              "NEVER ON CONFLICT DO NOTHING ON A CLIENT ID\n\n"
              "Under RLS it hides another user's row and reports a\n"
              "duplicate; the phone deletes the point. The batch looks\n"
              "up the caller's own ids; a 23505 is id_in_use.", w=420, colour=RED)
    e += note("nRed2", 1240, 220,
              "THE IDEMPOTENCY STORE REPLAYS A 4XX\n\n"
              "A new key per distinct payload (sha256 of the sorted\n"
              "point ids). A split batch under the old key replays\n"
              "batch_too_large for ever.", w=420, colour=RED)
    e += note("nRed3", 1240, 440,
              "A PERSON WRITES ONLY THEIR OWN ROWS\n\n"
              "Every insert and update checks user_id = me, at any\n"
              "scope. No ScopeSpec: its write branches check the office.\n"
              "Points carry the duty's office, so a transfer splits nothing.", w=420, colour=RED)
    e += note("nGreen1", 1240, 660,
              "No position in any event payload; visit events are for\n"
              "staff on the lead timeline. The board holds no tracking.", w=420, colour=GREEN)
    e += note("nYellow1", 1240, 820,
              "Stand-ins: hours Mon-Sat 9-7, photo optional, 90-day\n"
              "retention, our consent text (GAP-191 to GAP-201).", w=420, colour=YELLOW)
    write("29-field-tracking", e)


def _column(e: list, n: dict, steps: list, x: int) -> None:
    prev = None
    for i, (eid, lbl, colour) in enumerate(steps):
        els = node(eid, x, i * 120, lbl, w=520, h=90, colour=colour, size=14)
        n[eid] = els[0]
        e += els
        if prev:
            e += edge(f"e_{eid}", n[prev], n[eid])
        prev = eid


def f_payments() -> None:
    e, n = [], {}
    e += title("Payments: receipts, allocation, instalments, the ledger",
               sub="Accounts records money received and spreads it over orders; the order, the "
                   "inbox and the dealer ledger read a derived position (FS-022, ADR-045).",
               status="BUILT (backend). /payments, /orders/{id}/payment-schedule, "
                      "/partners/{id}/ledger; migration 031.",
               status_colour=GREEN)
    _column(e, n, [
        ("p1", "POST /payments {dealer, mode, ref, amount, allocations}\nAccounts, admin, MD only", BLUE),
        ("p2", "payment_record(): lock orders by id, check status,\ndealer, sums; receipt + allocations", VIOLET),
        ("p3", "events: payment.received (dealer),\npayment.allocated (each order); no amounts", VIOLET),
        ("p4", "order_payment_position(): payable, received, due\n-> status, overdue in the domain", GREEN),
    ], 0)
    _column(e, n, [
        ("q1", "PUT /orders/{id}/payment-schedule\n0 to 5 instalments, within payable", BLUE),
        ("q2", "GET /orders/{id} -> payments block\nGET /approvals/pending -> payment_status", GREEN),
        ("q3", "GET /partners/{id}/ledger\norders on approval, receipts in full", GREEN),
        ("q4", "POST /payments/{id}/void {reason}\nnever edited; allocations stop counting", BLUE),
    ], 620)
    e += note("nRed1", 1240, 0,
              "WRITES ARE DEFINERS\n\n"
              "Accounts holds no sales_orders.edit. Under RLS a FOR UPDATE\n"
              "it may not perform matches zero rows, so a direct write\n"
              "could not lock the orders it pays.", w=420, colour=RED)
    e += note("nRed2", 1240, 220,
              "NO AMOUNT IN ANY EVENT\n\n"
              "Order and lead timelines reach field officers and dealers,\n"
              "who hold no payments.view.", w=420, colour=RED)
    e += note("nRed3", 1240, 420,
              "POLICIES MUST NOT REFERENCE EACH OTHER\n\n"
              "payment_allocation carries the dealer, so the arrows run\n"
              "payment -> allocation -> order or dealer.", w=420, colour=RED)
    e += note("nYellow1", 1240, 620,
              "Stand-ins: payable = total, even closed short; ledger on\n"
              "approval; no debit to a dealer (GAP-205 to GAP-214).", w=420, colour=YELLOW)
    write("30-payments", e)


def f_stock() -> None:
    e, n = [], {}
    e += title("Stock: warehouses, the ledger, availability, dispatch",
               sub="A signed movement ledger; on hand and committed derived; a dispatch moves its "
                   "own warehouse (FS-023, ADR-046).",
               status="BUILT (backend). /warehouses, /stock, /stock/movements, "
                      "/stock/availability; migration 032.",
               status_colour=GREEN)
    _column(e, n, [
        ("s1", "POST /stock/movements: receipt or adjustment\nstock_record(): xact advisory lock, sorted", BLUE),
        ("s2", "stock_movement: signed, never edited\non hand = sum; committed = open order qty", GREEN),
        ("s3", "GET /stock/availability on the order form\nshort warns, never blocks", GREEN),
    ], 0)
    _column(e, n, [
        ("d1", "POST /orders/{id}/dispatches {warehouse_id?}\nelse the order's, else the default", BLUE),
        ("d2", "trigger on dispatch_line: -qty at the\ndispatch's warehouse (may go negative)", VIOLET),
        ("d3", "void: trigger negates the stored movement\nnever recomputed from the order", VIOLET),
    ], 620)
    e += note("nRed1", 1240, 0,
              "A SESSION ADVISORY LOCK OUTLIVES THE CLIENT\n\n"
              "Under PgBouncer it stays on the server connection.\n"
              "Use pg_advisory_xact_lock only.", w=420, colour=RED)
    e += note("nRed2", 1240, 200,
              "THE WAREHOUSE IS ON THE DISPATCH\n\n"
              "An approved order's warehouse cannot change: the\n"
              "submitted-order trigger refuses it.", w=420, colour=RED)
    e += note("nGreen1", 1240, 400,
              "Dealers and the board hold no stock permission.\n"
              "MAIN is seeded as the default.", w=420, colour=GREEN)
    e += note("nYellow1", 1240, 540,
              "Stand-ins: warn only; one default warehouse; no dealer\n"
              "stock (GAP-215 to GAP-218).", w=420, colour=YELLOW)
    write("31-stock", e)


def f_reports() -> None:
    e, n = [], {}
    e += title("Reports and the lead 360",
               sub="Live aggregates scoped like the lists; a figure without its module is null "
                   "(FS-024, ADR-047).",
               status="BUILT (backend). /reports/*, /leads/{id}/360; migration 034 (won_at, "
                      "lost_at). Excel through the exports writer (GAP-220 closed).",
               status_colour=GREEN)
    _column(e, n, [
        ("r1", "GET /reports/<name>?from&to&territory_id&owner_id\nreports.view + the base module, else 403", BLUE),
        ("r2", "aggregate: scope_predicate per table\n+ deleted_at IS NULL, RLS beneath", VIOLET),
        ("r2b", "orders: setting sale_counted_at picks the date (FS-026)\nsubmitted_at | approved_at | fully_dispatched_at |\norder_paid_at(); never draft, cancelled, short-and-unshipped", YELLOW),
        ("r3", "rows (1,000 max) + totals over everything\nnull for a figure without its module", GREEN),
    ], 0)
    _column(e, n, [
        ("l1", "lead stage change -> trigger sets\nwon_at / lost_at (every path)", VIOLET),
        ("l2", "GET /leads/{id}/360: tiles + same-mobile leads\nthe timeline is /leads/{id}/timeline", GREEN),
    ], 620)
    e += note("nRed1", 1240, 0,
              "RLS ALONE GIVES FALSE ZEROS\n\n"
              "Accounts holds no tasks or tracking; a State Co-ordinator\n"
              "no orders. A figure the caller cannot see is null.", w=420, colour=RED)
    e += note("nYellow1", 1240, 200,
              "Stand-ins: conversion = won / created; sales = commercial,\n"
              "industrial, export, subsidised (GAP-220 to GAP-226).", w=420, colour=YELLOW)
    e += note("nRed2", 1240, 340,
              "A NEW ORDER COLUMN MUST JOIN THE EDIT GUARD\n\n"
              "refuse_submitted_order_edit compares the whole row\n"
              "to an allow-list. 046 added fully_dispatched_at first;\n"
              "without it the status trigger's write raises.", w=420, colour=RED)
    e += note("nYellow2", 1240, 540,
              "SALE DATE (FS-026, 046)\n\n"
              "Default approval, admin-changeable; restates every period.\n"
              "Paid day = earliest receipt day whose running total of live\n"
              "allocations covers payable; a day, not an amount.\n"
              "Ordered value counts, not shipped (GAP-234 to GAP-239).", w=420, colour=YELLOW)
    write("32-reports", e)


def f_targets() -> None:
    e, n = [], {}
    e += title("Targets and achievement",
               sub="Monthly per-person targets; achievement through the reports' counting (FS-025).",
               status="BUILT (backend). /targets, /targets/achievement; migration 035.",
               status_colour=GREEN)
    _column(e, n, [
        ("t1", "PUT /targets {user, month, targets}\nbelow me: my subtree, not me, lower rank", BLUE),
        ("t2", "sales_target: append-only, latest wins\n+ target.set on the person", VIOLET),
        ("t3", "GET /targets/achievement?month\nme + everyone below, with or without targets\norders on the sale_counted_at date (FS-026)", GREEN),
    ], 0)
    e += note("nRed1", 620, 0,
              "THE SUBTREE HOLDS ME AND MY PEERS\n\n"
              "org_closure has self rows: a subtree test alone lets a\n"
              "manager set their own or a peer's target. Rank decides.", w=420, colour=RED)
    e += note("nYellow1", 620, 200,
              "A transfer moves this and later months (trigger).\n"
              "Stand-ins: four measures, monthly (GAP-230 to GAP-233).", w=420, colour=YELLOW)
    write("33-targets", e)


# ── session B, 3 Oct: canvases 40 to 49 ──────────────────────────────────────

def _columns(name: str, head: str, sub: str, status: str, steps: list, side: list,
             notes: list) -> None:
    """Main steps down the left, side steps down the middle, notes on the right."""
    e, n = [], {}
    e += title(head, sub=sub, status=status, status_colour=GREEN)
    for col, items, dashed in ((0, steps, False), (620, side, True)):
        prev = None
        for i, (eid, lbl, colour) in enumerate(items):
            els = node(eid, col, i * 120, lbl, w=520, h=90, colour=colour, size=14)
            n[eid] = els[0]
            e += els
            if prev:
                e += edge(f"e_{eid}", n[prev], n[eid], dashed=dashed)
            prev = eid
    y = 0
    for eid, text_, colour in notes:
        e += note(eid, 1240, y, text_, w=420, colour=colour)
        y += 260
    write(name, e)


def f_exports() -> None:
    _columns(
        "40-list-exports", "List exports: any list to Excel, through the list's own code",
        "Eight lists, one /export each, the same filters, the same scope.",
        "BUILT. FS-030: GET /<list>/export, no migration.",
        [("s1", "GET /leads/export?stage=new&territory_id=...\nfilters_of(list_leads): the list's own parameters", BLUE),
         ("s2", "the list endpoint itself, page by page\nthe caller's db and caller: service predicate + RLS", GREEN),
         ("s3", "more than 5,000 rows: 422 export_too_large\nnever a cut file", YELLOW),
         ("s4", "workbook(): typed cells, IST, frozen header\nbuilt in a thread", VIOLET),
         ("s5", "200 attachment leads-YYYY-MM-DD.xlsx\none structlog line: names of filters, never values", GREEN)],
        [("d1", "complaints awaiting=me: refused\nthe queue has no cursor", YELLOW),
         ("d2", "credit terms stay blank without partners.edit\nthe same masking code as the screen", GREEN)],
        [("n1", "A TEXT CELL STARTING = IS A FORMULA\n\nopenpyxl stores it as one through cell() and\nappend() alike. The writer forces data_type 's'.\nThe PIMS sheet had the same hole (ISS-200).", RED),
         ("n2", "/export IS DECLARED BEFORE /{id}\n\nStarlette matches {id} first; declared after,\nthe export answers 422 forever.", RED),
         ("n3", "Not yet: CSV, PDF, the client's layouts,\nlarge background exports (GAP-300 to GAP-303).", YELLOW)])


def f_schemes() -> None:
    _columns(
        "41-schemes", "Schemes: one order-status trigger writes every benefit",
        "Type 1 at submit; types 2 and 3 at delivery; type 4 nightly. A benefit lowers the payable, never the invoice.",
        "BUILT. FS-031: /schemes, /scheme-entitlements, GET /orders/{id}/schemes, migration 033.",
        [("s1", "admin: POST /schemes\ntype, condition, benefit, targets, dates", BLUE),
         ("s2", "draft order: GET /orders/{id}/schemes\nthe trigger's own functions, read-only", VIOLET),
         ("s3", "draft -> submitted: type 1 discounts, then credits\n(FOR UPDATE, earliest expiry, skip if larger)", GREEN),
         ("s4", "-> dispatched / closed_short: points and next-order credits\non dispatched quantities, latest dispatch day IST", GREEN),
         ("s5", "-> draft / cancelled: benefits reversed, credits released\nvoid out of dispatched: unused credits and points reversed", YELLOW)],
        [("d1", "nightly 00:20 IST: expire credits\nthen credit ended months and quarters", VIOLET),
         ("d2", "GET /orders/{id}: benefits + payable\npayments count against payable", GREEN),
         ("d3", "a dealer sees only schemes aimed at it\nnever their partner targets", GREY)],
        [("n1", "THE TRIGGER IS NAMED zz ON PURPOSE\n\nSame-event triggers fire alphabetically; the\nclose-short trigger writes qty_short first.", RED),
         ("n2", "UNIQUE ONLY AMONG ROWS NOT REVERSED\n\nA void reverses; the re-dispatch earns again.\nA plain unique index would refuse it for good.", RED),
         ("n3", "Every rule is a stand-in: product lines only, credit not\ninvoice, auto-use, dispatch date (GAP-304 to GAP-313).", YELLOW)])


def f_rewards() -> None:
    _columns(
        "42-rewards", "Reward points: earned by triggers, spent under one lock",
        "Dealers and staff earn; dealers spend on an order or a gift.",
        "BUILT. FS-032: /reward-rules, /reward-settings, /gifts, /rewards/*, migration 036.",
        [("s1", "order delivered: rule points for the partner\nand for a staff owner (before the no-partner return)", GREEN),
         ("s2", "lead won (any of three writers): lead_won points\nfor the staff owner, once per rule", GREEN),
         ("s3", "reward_spend(): advisory lock per holder\nbalance check, redemption + redeemed row", VIOLET),
         ("s4", "order redemption applied at submit\nafter scheme benefits; the rest released", BLUE),
         ("s5", "nightly: expire what is left of each due lot\noldest first", YELLOW)],
        [("d1", "gift: requested -> fulfilled / rejected / withdrawn\nreject and withdraw give the points back", BLUE),
         ("d2", "void: rule and scheme points reversed\nmay take a balance below zero", YELLOW)],
        [("n1", "A FIELD OFFICER READS NO DEALER'S POINTS\n\nrewards V:own: the ledger policy needs a partner\ncaller or a scope other than own (review B3).", RED),
         ("n2", "rewards.create IS HELD BY EVERY DEALER\n\nIt is how they redeem (GAP-043). Rules and gifts\nneed rewards.edit.", RED),
         ("n3", "Stand-ins: no rule until the admin adds one, Rs 1 a\npoint, 10% (GAP-316 to GAP-320, GAP-336).", YELLOW)])


def f_commission() -> None:
    _columns(
        "43-dealer-commission", "Dealer commission and TOD: subsidy stage 18",
        "After full FP: the co-ordinator records, Accounts approves and pays.",
        "BUILT. FS-033: /subsidy-applications/{id}/commission, /dealer-commissions, /commission-rates, migration 037.",
        [("s1", "full FP received, a dealer on the application\nGET .../commission/preview", BLUE),
         ("s2", "POST .../commission {gi, pvc, installation?}\nbase = cost excl GST - GI - PVC - installation", GREEN),
         ("s3", "Accounts: approve (not a recorder)\nor return with a remark", VIOLET),
         ("s4", "pay {date, reference}\ncompany-wide payments scope only", GREEN)],
        [("d1", "rate: one partner 4 + type 2 + system 1\nlatest start on or before the full-FP date", YELLOW),
         ("d2", "record again while calculated or returned\nclears the old decision", GREY)],
        [("n1", "A STATE MANAGER HOLDS payments.edit\n\nat org scope. Paying needs the global scope.", RED),
         ("n2", "Dealers do not see commissions (GAP-330).\nThe base and rates are our reading (GAP-321, GAP-323).", YELLOW)])


def f_marketing() -> None:
    _columns(
        "44-marketing-material", "Marketing material: order, approve over the office, dispatch",
        "17 items, company and dealer shares copied onto the order.",
        "BUILT. FS-034: /marketing-materials, /marketing-orders, migration 038.",
        [("s1", "catalogue: price and share, effective-dated\nnever edited; is_provisional stand-ins", BLUE),
         ("s2", "POST /marketing-orders: routed to the office\n(the lead rule); MM/<state>/<FY>/<n>", GREEN),
         ("s3", "District Manager over the office approves\nor rejects with a remark; never their own", VIOLET),
         ("s4", "marketing team: dispatched {date, reference}", GREEN)],
        [("d1", "marketing_order_refusal(): one rule for\nthe definer, can and awaiting=me", YELLOW),
         ("d2", "office use: no partner, 100% company", GREY)],
        [("n1", "create IS FOR ORDERING ONLY\n\nEvery ordering role holds it, dealers included.\nThe catalogue needs edit (review blocker).", RED),
         ("n2", "Not yet: images, budgets, billing the dealer's share,\nthe approver's bell (GAP-325 to GAP-335).", YELLOW)])


def f_subsidy_follow_ups() -> None:
    _columns(
        "45-subsidy-follow-ups", "Subsidy ageing, reports and masters revisions",
        "The client's six ageing figures, the stage and supply reports, and GGRC revisions from a date.",
        "BUILT. FS-009a: /subsidy-reports/*, /subsidy-masters/*, migration 039.",
        [("s1", "GET /subsidy-reports/ageing\nsix figures from the latest stage values", BLUE),
         ("s2", "GET /subsidy-reports/stages and /supply\neach with /export", BLUE),
         ("s3", "POST /subsidy-masters/{kind}/revisions\nfrom today or later; rows close and start", GREEN),
         ("s4", "POST /subsidy-masters/{matrix kind}/matrices\na new matrix; old cells never change", GREEN)],
        [("d1", "open interval: counted to today, running", YELLOW),
         ("d2", "engine cache cleared after a revision", GREY)],
        [("n1", "ROUTES UNDER /subsidy-reports\n\n/subsidy-applications/{app_id} would match /ageing first.", RED),
         ("n2", "Not yet: printed GGRC quotations and consent letters\n(GAP-331, GAP-333).", YELLOW)])


def f_lead_small_gaps() -> None:
    _columns(
        "46-lead-small-gaps", "Lead small gaps: QR edit, dormant leads, the office on assign",
        "Three pieces FS-003 and FS-003a left open.",
        "BUILT. FS-035: PATCH /lead-qr-codes/{id}, the nightly sweep, migration 040.",
        [("s1", "nightly 00:30 IST: lead_dormant_sweep(now, 2000)\nthe System principal only", VIOLET),
         ("s2", "open stage, no person's event for 60 days,\nno open task, no waiting quotation", BLUE),
         ("s3", "FOR UPDATE SKIP LOCKED, stage re-checked\nplain UPDATE: stage = dormant, from-stage kept", GREEN),
         ("s4", "POST /leads/{id}/reopen: back to the from-stage\nor transition to lost: lost_from = the from-stage", GREEN)],
        [("d1", "assign: the office follows the owner\nlead_owner_unit(), else routed by territory", BLUE),
         ("d2", "outside the assigner's scope: office kept", YELLOW),
         ("d3", "PATCH /lead-qr-codes/{id}: label, campaign,\ndealer, territory, switch off; the code never changes", GREY)],
        [("n1", "THE CLEAR TRIGGER GUARDS THE CHECK\n\nA merge moves a dormant loser to merged. Without\ntrg_lead_dormant_clear the CHECK fails with a 500.", RED),
         ("n2", "DO NOT RUN THE SWEEP ON THE DEV DB\n\nIt parks every idle demo lead. The tests run it\n61 days ahead inside a rolled-back transaction.", RED),
         ("n3", "Ours: 60 days, what keeps a lead open, only Reopen\nwakes it, nobody told (GAP-339 to GAP-342).", YELLOW)])


def f_settings_amend_reopen() -> None:
    _columns(
        "47-settings-amend-reopen", "Company settings, amending an approved order, reopening a complaint",
        "Client blockers built as admin settings with our defaults.",
        "BUILT. FS-036: /settings, POST /orders/{id}/amend, POST /complaints/{id}/reopen, migration 041.",
        [("s1", "PATCH /settings (masters.edit)\napp_setting_set(): checked, one setting.changed event", YELLOW),
         ("s2", "POST /orders/{id}/amend {remark}: staff only\napproved, nothing dispatched, no payment allocated", BLUE),
         ("s3", "order_amend(): approved -> draft, amend_count + 1\nschedule cleared, PDF withdrawn, scheme benefits reversed", GREEN),
         ("s4", "resubmit: order_amend_reapproval\nalways = the full chain; value_rises = Accounts + Dispatch\nunless the total went above amended_from_total", YELLOW)],
        [("r1", "POST /complaints/{id}/reopen {reason}\nclosed or qc_rejected, inside the window, under the cap", BLUE),
         ("r2", "who: the raiser for a closed one;\ncomplaint_reopen_roles for a rejection", YELLOW),
         ("r3", "a new round: submitted, submit_count + 1\nrestart: targets from now; continue: original targets", GREEN),
         ("r4", "complaint.submitted (reopened: true)\nthe checker's queue and the bell need nothing new", GREEN)],
        [("n1", "A DEALER MUST NOT AMEND\n\nPortal roles hold sales_orders.edit at partner_subtree.\norder_amend() refuses any partner caller (review F-1).", RED),
         ("n2", "THE SEED INSERT SKIPS THE ROLE CHECK\n\nRoles are seeded after migrating, and 005/015 already\ninsert roles, so 'table empty' never fired. INSERT skips;\nevery change is checked.", RED),
         ("n3", "A reopen nobody can check is refused (no_checker),\nas a submit is. An amended draft needs delete to cancel.", GREEN),
         ("n4", "Ours: every default in /settings\n(GAP-343 to GAP-348).", YELLOW)])


def f_dealer_tasks() -> None:
    _columns(
        "48-dealer-tasks", "Tasks for dealers",
        "A manager assigns a task to a dealer's user; the dealer completes it.",
        "BUILT, OFF BY DEFAULT. FS-037: setting tasks_for_dealers, migration 042.",
        [("s1", "admin: tasks_for_dealers = on", YELLOW),
         ("s2", "GET /tasks/assignees?include_partners=true\ntask_partner_assignees(): dealers the caller can see", BLUE),
         ("s3", "POST /tasks: authz_user_assignable('tasks')\npartner arm: caller assigns downwards, setting on", BLUE),
         ("s4", "the task lives in the assigner's office;\nthe link must be visible to the dealer", GREEN),
         ("s5", "dealer: GET /tasks?assigned_to=me,\nPOST /tasks/{id}/complete", GREEN)],
        [("d1", "dealer: patch, cancel, reopen, create -> 403", RED),
         ("d2", "task_partner_guard(): completion columns only (42501)", GREEN),
         ("d3", "setting off: require('tasks') refuses a dealer,\nget_caller drops tasks; dashboard shows null", YELLOW)],
        [("n1", "OFF MEANS NO TASKS, IN THE API ONLY\n\nRLS still shows a dealer its own old task rows and\ntimeline events after a switch-off (GAP-353).", RED),
         ("n2", "The arm is tasks-only: leads call the same\nauthz_user_assignable and must not reach dealers.", RED),
         ("n3", "Ours: off by default; a dealer only completes;\nclosing a dealer leaves tasks open (GAP-349 to GAP-351).", YELLOW)])


def f_whatsapp_webhook() -> None:
    _columns(
        "49-whatsapp-webhook-capture", "WhatsApp webhook capture",
        "Step one: keep what 11za sends, exactly as it arrived. Step two reads it.",
        "BUILT. FS-038: two public routes, migration 043, scripts/whatsapp_webhook.py.",
        [("s1", "11za calls GET/HEAD/POST\n/api/v1/public/webhooks/whatsapp/{secret}/inbound|status", GREY),
         ("s2", "UploadLimit: over 64 KB -> 413,\nbefore the body is read", BLUE),
         ("s3", "secret as bytes, constant time;\nwrong or unset -> 404, no session opened", BLUE),
         ("s4", "whatsapp_webhook_record() as app_anon:\nmethod, address, header pairs, raw bytes", GREEN),
         ("s5", "200 {ok: true}. Nothing else happens yet", GREEN)],
        [("d1", "nightly purge_expired_sessions:\nwhatsapp_webhook_purge(now - 30 days)", VIOLET),
         ("d2", "script: get / register --base-url / delete --type\nevery command ends with a get", YELLOW),
         ("d3", "FS-038b: inbound -> lead (source whatsapp),\nstatus -> outbox delivered/read", GREY)],
        [("n1", "THE SECRET IS IN THE URL\n\nEvery path that reaches a log goes through redact_path():\nstructlog path, the 500 handler, uvicorn.access.\nNew code that logs a path must use it too.", RED),
         ("n2", "11ZA SIGNS NOTHING\n\nThe path secret is the only lock until we know\n11za's addresses (GAP-355).", RED),
         ("n3", "Ours: 30 days kept, no rate limit, a call during\na DB outage is lost (GAP-356, GAP-357).", YELLOW)])


if __name__ == "__main__":
    print("generating flows:")
    f_system(); f_request(); f_permissions(); f_lead()
    f_approval(); f_subsidy(); f_outbox(); f_money(); f_pricing()
    f_quotation(); f_order(); f_auth(); f_admin(); f_tasks(); f_complaints(); f_bell_and_messages()
    f_subsidy_applications(); f_field_tracking(); f_payments(); f_stock()
    f_reports(); f_targets()
    f_exports(); f_schemes(); f_rewards(); f_commission(); f_marketing()
    f_subsidy_follow_ups(); f_lead_small_gaps()
    f_settings_amend_reopen(); f_dealer_tasks(); f_whatsapp_webhook()
    print(f"\nwrote to {OUT}")
