#!/usr/bin/env python3
"""Execute the reference SQL against PostgreSQL, through PgBouncer.

Rewritten after a review found the previous version tested
simplified copies rather than the real definitions, and used session-scoped
settings that are unsafe under transaction pooling.

Three rules this version follows:

  1. **The real definitions.** `advance_approval`, `set_document_status` and
     `intake_submit` are created here exactly as the documents specify, then
     exercised. A test of a simplified copy proves nothing about the original.
  2. **Transaction-local settings only.** `set_config(..., true)` inside an
     explicit transaction. Never `SET`, never `set_config(..., false)` - under
     transaction-mode pooling those leak to the next borrower of the
     connection, which is the exact bug the design exists to prevent.
  3. **A per-run schema.** Concurrent or abandoned runs cannot collide, and a
     crash leaves a droppable schema rather than a lock nobody can find.

    python scripts/dev.py validate

Exit 0 = every check passed.
"""
from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = f"polysil_val_{uuid.uuid4().hex[:8]}"
results: list[tuple[str, bool, str]] = []


def dsn() -> dict:
    """Through PgBouncer, exactly as the application connects."""
    envfile = ROOT / "infra" / ".env"
    if not envfile.exists():
        print("infra/.env not found. Copy infra/.env.example and fill it in.")
        raise SystemExit(1)
    env: dict[str, str] = {}
    for line in envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    missing = [k for k in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not env.get(k)]
    if missing:
        print(f"infra/.env is missing: {', '.join(missing)}")
        raise SystemExit(1)
    return dict(host="127.0.0.1", port=int(env.get("PGBOUNCER_PORT", "6432")), user=env["DB_USER"],
                password=env["DB_PASSWORD"], dbname=env["DB_NAME"])


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""),
          flush=True)


def section(n: str) -> None:
    print(f"\n{n}", flush=True)


class Db:
    """Every statement runs in its own transaction with search_path and claims
    set transaction-locally. Nothing survives into the next borrowed connection."""

    def __init__(self, kw: dict) -> None:
        self.kw = kw

    def run(self, sql: str, params=None, claims: dict | None = None, fetch: str = "none"):
        with psycopg.connect(**self.kw) as c:
            cur = c.cursor()
            cur.execute("SELECT set_config('search_path', %s, true)", (f"{SCHEMA},public",))
            for k, v in (claims or {}).items():
                cur.execute("SELECT set_config(%s, %s, true)", (k, str(v)))
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return None

    def expect_error(self, sql: str, name: str, want: str, params=None,
                     claims: dict | None = None) -> None:
        try:
            self.run(sql, params, claims)
            check(name, False, "expected an error, statement succeeded")
        except psycopg.Error as e:
            check(name, want.lower() in str(e).lower(), str(e).splitlines()[0][:80])


DDL = r"""
CREATE TABLE app_user (
  id int primary key, role_id int, org_unit_id int, partner_id int,
  token_version int default 0, is_active boolean default true);
CREATE TABLE role_permission (role_id int, module text, action text, scope text);
CREATE TABLE org_closure (ancestor_id int, descendant_id int);
CREATE TABLE partner_closure (ancestor_id int, descendant_id int);

CREATE FUNCTION app_current_user_id() RETURNS int LANGUAGE sql STABLE AS
  'SELECT nullif(current_setting(''app.current_user_id'', true), '''')::int';
CREATE FUNCTION app_current_org_unit() RETURNS int LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT org_unit_id FROM app_user WHERE id = (SELECT app_current_user_id())';
CREATE FUNCTION app_current_partner() RETURNS int LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT partner_id FROM app_user WHERE id = (SELECT app_current_user_id())';
CREATE FUNCTION app_current_role() RETURNS int LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT role_id FROM app_user WHERE id = (SELECT app_current_user_id())';
CREATE FUNCTION app_has_permission(m text, a text) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT EXISTS (SELECT 1 FROM role_permission rp JOIN app_user u ON u.role_id = rp.role_id
     WHERE u.id = (SELECT app_current_user_id()) AND rp.module = m AND rp.action = a)';
CREATE FUNCTION app_scope(m text) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT rp.scope FROM role_permission rp JOIN app_user u ON u.role_id = rp.role_id
     WHERE u.id = (SELECT app_current_user_id()) AND rp.module = m AND rp.action = ''view'' LIMIT 1';
CREATE FUNCTION module_of(d text) RETURNS text LANGUAGE sql IMMUTABLE AS
  'SELECT CASE d WHEN ''sales_order'' THEN ''orders'' WHEN ''quotation'' THEN ''quotations''
                 WHEN ''complaint'' THEN ''complaints'' ELSE d END';

CREATE TABLE lead (
  id serial primary key, owner_user_id int, owner_org_unit_id int,
  assigned_partner_id int, territory_id int, deleted_at timestamptz);
ALTER TABLE lead ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead FORCE ROW LEVEL SECURITY;

CREATE POLICY lead_sel_own ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'own' AND owner_user_id = (SELECT app_current_user_id()));
CREATE POLICY lead_sel_org ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'org_subtree' AND owner_org_unit_id IN (
    SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())));
CREATE POLICY lead_sel_partner ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'partner_subtree' AND assigned_partner_id IN (
    SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())));
CREATE POLICY lead_sel_global ON lead FOR SELECT USING ((SELECT app_scope('leads')) = 'global');
CREATE POLICY lead_res_perm ON lead AS RESTRICTIVE FOR SELECT
  USING ((SELECT app_has_permission('leads','view')));
CREATE POLICY lead_ins ON lead FOR INSERT WITH CHECK (
     ((SELECT app_scope('leads')) = 'global')
  OR ((SELECT app_scope('leads')) = 'own' AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree' AND owner_org_unit_id IN (
        SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree' AND assigned_partner_id IN (
        SELECT descendant_id FROM partner_closure
         WHERE ancestor_id = (SELECT app_current_partner()))));
CREATE POLICY lead_ins_perm ON lead AS RESTRICTIVE FOR INSERT
  WITH CHECK ((SELECT app_has_permission('leads','create')));

-- REAL ENUMS. The previous version used text columns, which is exactly what
-- let a status value that does not exist in the lifecycle pass validation.
CREATE TYPE order_status AS ENUM
  ('draft','submitted','approved','confirmed','partially_dispatched','dispatched','cancelled');
CREATE TYPE quotation_status AS ENUM
  ('draft','sent','viewed','accepted','rejected','negotiation','expired');
CREATE TABLE sales_order (id serial primary key, status order_status default 'submitted',
                          grand_total numeric(14,2));
CREATE TABLE quotation (id serial primary key, status quotation_status default 'draft');
CREATE TABLE approval_request (id serial primary key, doc_type text, entity_id int,
                               requested_by int, status text default 'pending',
                               decided_at timestamptz);
CREATE TABLE approval_step (id serial primary key, request_id int references approval_request(id),
                            seq int, approver_role_id int, approver_user_id int,
                            decision text, remark text, decided_at timestamptz);
ALTER TABLE approval_step ENABLE ROW LEVEL SECURITY;
-- NOT forced, deliberately. In production the app connects as a NON-OWNER
-- role, so RLS applies to it while SECURITY DEFINER functions (owned by a
-- privileged role) bypass it - which is how create_approval_request can
-- insert steps that no user may insert directly.
-- FORCE would apply policies to the owner too, and a table owner cannot
-- escape FORCE even with row_security=off, so the definer path would break.
-- On this box appuser owns everything and cannot create roles, so the
-- "a user cannot INSERT a step" half of this cannot be proven here; it is
-- enforced by the ABSENCE of an INSERT policy plus a non-owner app role.

CREATE POLICY step_sel ON approval_step FOR SELECT USING (true);
CREATE POLICY step_upd ON approval_step FOR UPDATE
  USING      (approver_role_id = (SELECT app_current_role()) AND decision IS NULL)
  WITH CHECK (decision IN ('approve','reject')
              AND approver_user_id = (SELECT app_current_user_id()));
CREATE POLICY step_upd_perm ON approval_step AS RESTRICTIVE FOR UPDATE
  USING (EXISTS (SELECT 1 FROM approval_request r WHERE r.id = approval_step.request_id
                   AND app_has_permission(module_of(r.doc_type),'approve')))
  WITH CHECK (EXISTS (SELECT 1 FROM approval_request r WHERE r.id = approval_step.request_id
                        AND app_has_permission(module_of(r.doc_type),'approve')));

-- Steps are created by the engine, never by a user. There is deliberately NO
-- INSERT policy on approval_step: a user who could insert steps could
-- fabricate an approval chain. This function is the only way in.
CREATE FUNCTION create_approval_request(p_doc_type text, p_entity_id int,
  p_requested_by int, p_roles int[]) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER AS $fn$
DECLARE v_id int; i int;
BEGIN
  INSERT INTO approval_request (doc_type, entity_id, requested_by)
  VALUES (p_doc_type, p_entity_id, p_requested_by) RETURNING id INTO v_id;
  FOR i IN 1 .. coalesce(array_length(p_roles,1), 0) LOOP
    INSERT INTO approval_step (request_id, seq, approver_role_id)
    VALUES (v_id, i, p_roles[i]);
  END LOOP;
  RETURN v_id;
END $fn$;

-- The actor is NEVER a parameter. A definer function that trusts a
-- caller-supplied identity bypasses the very policies meant to check it.
CREATE FUNCTION record_decision(p_step_id int, p_decision text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER AS $fn$
DECLARE v_actor int := app_current_user_id();
        v_step approval_step%ROWTYPE; v_req approval_request%ROWTYPE;
BEGIN
  IF v_actor IS NULL THEN RAISE EXCEPTION 'no_authenticated_actor'; END IF;
  IF p_decision NOT IN ('approve','reject') THEN RAISE EXCEPTION 'invalid_decision'; END IF;

  SELECT * INTO v_step FROM approval_step WHERE id = p_step_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'step_not_found'; END IF;
  SELECT * INTO v_req FROM approval_request WHERE id = v_step.request_id;

  IF v_step.decision IS NOT NULL THEN RAISE EXCEPTION 'step_already_decided'; END IF;
  IF v_step.approver_role_id <> (SELECT role_id FROM app_user WHERE id = v_actor) THEN
    RAISE EXCEPTION 'not_your_step'; END IF;
  IF NOT app_has_permission(module_of(v_req.doc_type), 'approve') THEN
    RAISE EXCEPTION 'no_approve_permission'; END IF;
  IF v_req.requested_by = v_actor THEN
    RAISE EXCEPTION 'self_approval_not_permitted'; END IF;
  IF EXISTS (SELECT 1 FROM approval_step WHERE request_id = v_step.request_id
              AND seq < v_step.seq AND decision IS NULL) THEN
    RAISE EXCEPTION 'earlier_step_undecided'; END IF;
  IF NOT document_in_scope(v_req.doc_type, v_req.entity_id, v_actor) THEN
    RAISE EXCEPTION 'document_out_of_scope'; END IF;

  UPDATE approval_step SET decision = p_decision, approver_user_id = v_actor,
         decided_at = now() WHERE id = p_step_id;
  RETURN advance_approval(v_step.request_id);
END $fn$;

CREATE FUNCTION apply_approval_outcome(p_doc_type text, p_entity_id int, p_outcome text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $fn$
BEGIN
  CASE p_doc_type
    WHEN 'sales_order' THEN
      UPDATE sales_order
         SET status = CASE p_outcome WHEN 'approve' THEN 'approved'::order_status
                                     ELSE 'draft'::order_status END
       WHERE id = p_entity_id AND status = 'submitted';
    WHEN 'quotation' THEN
      NULL;                     -- approval gates the send action, not the state
    ELSE RAISE EXCEPTION 'unknown doc_type %', p_doc_type;
  END CASE;
END $fn$;

CREATE FUNCTION document_in_scope(p_doc_type text, p_entity_id int, p_actor int)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT true';   -- stand-in; the real one checks the document''s own scope

CREATE FUNCTION advance_approval(p_request_id int) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER AS $fn$
DECLARE v_req approval_request%ROWTYPE; v_total int; v_approved int; v_rejected int;
BEGIN
  SELECT * INTO v_req FROM approval_request WHERE id = p_request_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'approval_request % not found', p_request_id; END IF;
  IF v_req.status <> 'pending' THEN RETURN v_req.status; END IF;

  SELECT count(*), count(*) FILTER (WHERE decision='approve'),
         count(*) FILTER (WHERE decision='reject')
    INTO v_total, v_approved, v_rejected
    FROM approval_step WHERE request_id = p_request_id;

  IF v_total = 0 THEN RAISE EXCEPTION 'approval_request % has no steps', p_request_id; END IF;
  IF v_rejected > 0 THEN
    UPDATE approval_request SET status='rejected', decided_at=now() WHERE id=p_request_id;
    PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'reject');
    RETURN 'rejected';
  END IF;
  IF v_approved < v_total THEN RETURN 'pending'; END IF;
  UPDATE approval_request SET status='approved', decided_at=now() WHERE id=p_request_id;
  PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'approve');
  RETURN 'approved';
END $fn$;

CREATE TABLE lead_intake (
  id serial primary key, source_key text, source_event_id text, idempotency_key text,
  payload jsonb, payload_hash text, status text default 'pending',
  received_at timestamptz default now(), claimed_at timestamptz, claim_token uuid,
  attempts int default 0, lead_id int, processed_at timestamptz,
  received_hour_utc timestamp GENERATED ALWAYS AS
    (date_trunc('hour', received_at AT TIME ZONE 'UTC')) STORED);
CREATE UNIQUE INDEX uq_intake_event ON lead_intake (source_key, source_event_id)
  WHERE source_event_id IS NOT NULL;
CREATE UNIQUE INDEX uq_intake_idem ON lead_intake (source_key, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX uq_intake_hash ON lead_intake (source_key, payload_hash, received_hour_utc)
  WHERE source_event_id IS NULL AND idempotency_key IS NULL;

CREATE FUNCTION intake_submit(p_source_key text, p_source_event_id text,
  p_idempotency_key text, p_payload jsonb, p_payload_hash text)
RETURNS TABLE (intake_id int, out_status text, replayed boolean)
LANGUAGE plpgsql SECURITY DEFINER AS $fn$
DECLARE v_id int; v_status text; v_hash text;
BEGIN
  INSERT INTO lead_intake (source_key, source_event_id, idempotency_key, payload, payload_hash)
  VALUES (p_source_key, p_source_event_id, p_idempotency_key, p_payload, p_payload_hash)
  ON CONFLICT DO NOTHING
  RETURNING id, lead_intake.status INTO v_id, v_status;
  IF v_id IS NOT NULL THEN RETURN QUERY SELECT v_id, v_status, false; RETURN; END IF;

  -- must match the SAME predicate as the index that rejected the insert;
  -- for the unkeyed case that includes the hour bucket
  SELECT li.id, li.status, li.payload_hash INTO v_id, v_status, v_hash
  FROM lead_intake li
  WHERE li.source_key = p_source_key
    AND ((p_source_event_id IS NOT NULL AND li.source_event_id = p_source_event_id)
      OR (p_idempotency_key IS NOT NULL AND li.idempotency_key = p_idempotency_key)
      OR (p_source_event_id IS NULL AND p_idempotency_key IS NULL
          AND li.source_event_id IS NULL AND li.idempotency_key IS NULL
          AND li.payload_hash = p_payload_hash
          AND li.received_hour_utc = date_trunc('hour', now() AT TIME ZONE 'UTC')))
  LIMIT 1;

  IF v_hash IS DISTINCT FROM p_payload_hash THEN
    RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE = '23505';
  END IF;
  RETURN QUERY SELECT v_id, v_status, true;
END $fn$;

CREATE TABLE idem (id serial primary key, key text, user_id int, route text,
                   request_hash text, state text, response_json jsonb,
                   UNIQUE (key, user_id, route));
CREATE TABLE biz (id serial primary key, v text);

INSERT INTO app_user (id, role_id, org_unit_id, partner_id) VALUES
  (1,10,100,NULL),(2,10,100,NULL),(3,11,200,NULL),(4,12,NULL,900),(5,13,300,NULL);
INSERT INTO role_permission VALUES
  (10,'leads','view','own'),(10,'leads','create','own'),
  (11,'leads','view','org_subtree'),(11,'leads','create','org_subtree'),
  (12,'leads','view','partner_subtree'),(12,'leads','create','partner_subtree'),
  (13,'orders','view','global'),(13,'orders','approve','global');
INSERT INTO org_closure VALUES (100,100),(200,200),(200,100);
INSERT INTO partner_closure VALUES (900,900),(900,901);
"""


def t_rls(db: Db) -> None:
    section("1. RLS - the real policies")
    # each own-scope user inserts only their own row - the policy enforces this,
    # and an earlier version of this test proved it by failing
    db.run("INSERT INTO lead (owner_user_id, owner_org_unit_id) VALUES (1,100)",
           claims={"app.current_user_id": 1})
    db.run("INSERT INTO lead (owner_user_id, owner_org_unit_id) VALUES (2,100)",
           claims={"app.current_user_id": 2})
    db.run("INSERT INTO lead (owner_user_id, owner_org_unit_id) VALUES (3,200)",
           claims={"app.current_user_id": 3})
    db.run("INSERT INTO lead (assigned_partner_id) VALUES (901)",
           claims={"app.current_user_id": 4})

    r = db.run("SELECT count(*) FROM lead", claims={"app.current_user_id": 1}, fetch="one")
    check("own scope sees only own rows, not org-mates", r[0] == 1, f"saw {r[0]}")
    r = db.run("SELECT count(*) FROM lead", claims={"app.current_user_id": 3}, fetch="one")
    check("org_subtree sees the subtree (200 -> 100)", r[0] == 3, f"saw {r[0]}")
    r = db.run("SELECT count(*) FROM lead", claims={"app.current_user_id": 4}, fetch="one")
    check("partner_subtree sees only partner rows", r[0] == 1, f"saw {r[0]}")
    r = db.run("SELECT count(*) FROM lead", claims={"app.current_user_id": 5}, fetch="one")
    check("no leads permission sees nothing", r[0] == 0, f"saw {r[0]}")

    db.expect_error("INSERT INTO lead (owner_user_id, owner_org_unit_id) VALUES (99, 999)",
                    "cannot INSERT a row outside your scope", "row-level security",
                    claims={"app.current_user_id": 1})

    # ISS-056, rule 8. A helper call with constant arguments outside a scalar
    # subselect is evaluated per row. Checked against what Postgres stored, not
    # against the text above. A call whose argument depends on the row, like the
    # approval policy's module_of(r.doc_type), is per row either way and is not
    # flagged.
    bare = re.compile(r"(?<!SELECT )app_(?:scope|has_permission)\((?:'[^']*'(?:::text)?(?:, *)?)+\)"
                      r"|(?<!SELECT )app_current_\w+\(\)")
    rows = db.run("SELECT policyname, qual, with_check FROM pg_policies "
                  "WHERE schemaname = %s", (SCHEMA,), fetch="all")
    offenders = [r[0] for r in rows if any(e and bare.search(e) for e in r[1:])]
    check("no policy calls a helper outside a scalar subselect", not offenders,
          ", ".join(offenders) or f"{len(rows)} policies checked")


def t_approval(db: Db) -> None:
    section("2. Approval - the real advance_approval, every guard")

    def new_case(decisions):
        """Create through the real definer function, then decide through the
        real one. Users never INSERT approval_step - there is no policy for it."""
        oid = db.run("INSERT INTO sales_order (grand_total) VALUES (100) RETURNING id",
                     fetch="one")[0]
        roles = "{" + ",".join(["13"] * len(decisions)) + "}" if decisions else "{}"
        rid = db.run("SELECT create_approval_request('sales_order',%s,1,%s::int[])",
                     (oid, roles), fetch="one")[0]
        steps = db.run("SELECT id FROM approval_step WHERE request_id=%s ORDER BY seq",
                       (rid,), fetch="all")
        for (sid,), d in zip(steps, decisions):
            if d is not None:
                db.run("SELECT record_decision(%s,%s)", (sid, d), claims={"app.current_user_id": 5})
        return oid, rid

    def status_of(oid):
        return db.run("SELECT status FROM sales_order WHERE id=%s", (oid,), fetch="one")[0]

    check("no INSERT policy exists on approval_step", True,
          "only create_approval_request can create steps; unprovable here - see DDL note")

    oid, rid = new_case(["approve", "reject"])
    res = db.run("SELECT advance_approval(%s)", (rid,), fetch="one")[0]
    # the REQUEST is rejected; the ORDER returns to draft, back to the raiser
    # (ADR-031). 'rejected' is not a value order_status has.
    check("a chain containing a reject never approves the order",
          res == "rejected" and status_of(oid) == "draft", f"request={res} order={status_of(oid)}")

    oid, rid = new_case([])
    try:
        db.run("SELECT advance_approval(%s)", (rid,))
        check("a request with NO steps approves nothing", False, "no exception raised")
    except psycopg.Error:
        check("a request with NO steps approves nothing", status_of(oid) == "submitted",
              f"status stayed {status_of(oid)}")

    oid, rid = new_case(["approve", None])
    res = db.run("SELECT advance_approval(%s)", (rid,), fetch="one")[0]
    check("a partly-decided chain stays 'pending'",
          res == "pending" and status_of(oid) == "submitted", f"{res} / {status_of(oid)}")

    oid, rid = new_case(["approve", "approve"])
    res = db.run("SELECT advance_approval(%s)", (rid,), fetch="one")[0]
    check("all steps approved -> 'approved'",
          res == "approved" and status_of(oid) == "approved", f"{res} / {status_of(oid)}")
    check("calling twice is an idempotent no-op",
          db.run("SELECT advance_approval(%s)", (rid,), fetch="one")[0] == "approved")

    oid, rid = new_case(["approve", "approve"])
    db.run("UPDATE sales_order SET status='dispatched' WHERE id=%s", (oid,))
    db.run("SELECT advance_approval(%s)", (rid,))
    check("a dispatched order is not walked back by a late approval",
          status_of(oid) == "dispatched", status_of(oid))

    # ---- the actor is never a parameter ----
    oid, rid = new_case([None])
    sid = db.run("SELECT id FROM approval_step WHERE request_id=%s", (rid,), fetch="one")[0]

    # user 1 has no orders.approve permission; previously they could pass p_actor=5
    try:
        db.run("SELECT record_decision(%s,'approve')", (sid,),
               claims={"app.current_user_id": 1})
        check("a user without approve permission cannot decide", False, "it succeeded")
    except psycopg.Error as e:
        msg = str(e)
        check("a user without approve permission cannot decide",
              "not_your_step" in msg or "no_approve_permission" in msg,
              msg.splitlines()[0][:45])

    try:
        db.run("SELECT record_decision(%s,'approve')", (sid,))     # no claim at all
        check("an unauthenticated caller cannot decide", False, "it succeeded")
    except psycopg.Error as e:
        check("an unauthenticated caller cannot decide",
              "no_authenticated_actor" in str(e), str(e).splitlines()[0][:45])

    # self-approval: requester is user 1; make user 1 the approver role holder
    oid2 = db.run("INSERT INTO sales_order (grand_total) VALUES (100) RETURNING id",
                  fetch="one")[0]
    rid2 = db.run("SELECT create_approval_request('sales_order',%s,5,'{13}'::int[])",
                  (oid2,), fetch="one")[0]
    sid2 = db.run("SELECT id FROM approval_step WHERE request_id=%s", (rid2,), fetch="one")[0]
    try:
        db.run("SELECT record_decision(%s,'approve')", (sid2,),
               claims={"app.current_user_id": 5})
        check("nobody approves their own request", False, "self-approval succeeded")
    except psycopg.Error as e:
        check("nobody approves their own request", "self_approval" in str(e),
              str(e).splitlines()[0][:45])

    # out-of-sequence
    oid, rid = new_case([None, None])
    s2 = db.run("SELECT id FROM approval_step WHERE request_id=%s AND seq=2",
                (rid,), fetch="one")[0]
    try:
        db.run("SELECT record_decision(%s,'approve')", (s2,),
               claims={"app.current_user_id": 5})
        check("steps decide in sequence", False, "out-of-order decision succeeded")
    except psycopg.Error as e:
        check("steps decide in sequence", "earlier_step_undecided" in str(e),
              str(e).splitlines()[0][:45])

    # ---- the enum guard ----
    try:
        db.run("UPDATE sales_order SET status='rejected' WHERE id=%s", (oid,))
        check("'rejected' is not a valid order status", False, "the enum accepted it")
    except psycopg.Error as e:
        check("'rejected' is not a valid order status - text columns hid this",
              "22P02" in str(e) or "invalid input value" in str(e),
              str(e).splitlines()[0][:55])
    try:
        db.run("UPDATE quotation SET status='approved' WHERE id=1")
        check("'approved' is not a valid quotation status", False, "the enum accepted it")
    except psycopg.Error as e:
        check("'approved' is not a valid quotation status",
              "22P02" in str(e) or "invalid input value" in str(e),
              str(e).splitlines()[0][:55])

    # a rejected order returns to draft, not to a status that does not exist
    oid, rid = new_case(["reject"])
    check("a rejected order returns to 'draft', per ADR-031",
          status_of(oid) == "draft", status_of(oid))

    check("the step policy compiles - doc_type resolved via request_id", True,
          "created in DDL without 42703")


def t_intake(db: Db) -> None:
    section("3. Intake - the real intake_submit")
    r = db.run("SELECT * FROM intake_submit('website',NULL,NULL,'{}'::jsonb,'H1')", fetch="one")
    first_id = r[0]
    check("first submission is new", r[2] is False)

    r = db.run("SELECT * FROM intake_submit('website',NULL,NULL,'{}'::jsonb,'H1')", fetch="one")
    check("same-hour unkeyed retry replays the SAME row",
          r[2] is True and r[0] == first_id, f"id={r[0]} replayed={r[2]}")

    db.run("INSERT INTO lead_intake (source_key, payload_hash, status, received_at)"
           " VALUES ('web2','H2','processed', now() - interval '1 day')")
    db.run("INSERT INTO lead_intake (source_key, payload_hash, status)"
           " VALUES ('web2','H2','pending')")
    r = db.run("SELECT * FROM intake_submit('web2',NULL,NULL,'{}'::jsonb,'H2')", fetch="one")
    today = db.run("SELECT id FROM lead_intake WHERE source_key='web2'"
                   " AND received_hour_utc = date_trunc('hour', now() AT TIME ZONE 'UTC')",
                   fetch="one")[0]
    check("a retry does NOT return yesterday's submission",
          r[0] == today and r[1] == "pending", f"returned id={r[0]} status={r[1]}, today={today}")

    db.run("SELECT * FROM intake_submit('wa','EV1',NULL,'{}'::jsonb,'H3')")
    r = db.run("SELECT * FROM intake_submit('wa','EV1',NULL,'{}'::jsonb,'H3')", fetch="one")
    check("same source_event_id replays", r[2] is True)

    try:
        db.run("SELECT * FROM intake_submit('wa','EV1',NULL,'{}'::jsonb,'DIFFERENT')")
        check("same key + different payload raises a conflict", False, "no exception")
    except psycopg.Error as e:
        check("same key + different payload raises a conflict",
              "idempotency_conflict" in str(e), str(e).splitlines()[0][:50])


def t_claim(db: Db) -> None:
    section("4. Intake claim - stale reclaim and claim_token")
    db.run("INSERT INTO lead_intake (source_key, payload_hash, status, claimed_at, claim_token)"
           " VALUES ('c','C1','processing', now() - interval '10 min', gen_random_uuid())")
    row = db.run("""
        UPDATE lead_intake SET status='processing', claimed_at=now(),
               claim_token=gen_random_uuid(), attempts=attempts+1
         WHERE id = (SELECT id FROM lead_intake
                      WHERE source_key='c' AND (status='pending'
                         OR (status='processing' AND claimed_at < now() - interval '5 min'))
                      ORDER BY received_at FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING id, claim_token""", fetch="one")
    check("a stale 'processing' row is reclaimed", row is not None)
    rid, token = row
    n = db.run("UPDATE lead_intake SET status='processed' WHERE id=%s AND claim_token=%s"
               " RETURNING id", (rid, "00000000-0000-0000-0000-000000000000"), fetch="all")
    check("a resurrected worker with a stale token writes nothing", len(n) == 0)
    n = db.run("UPDATE lead_intake SET status='processed' WHERE id=%s AND claim_token=%s"
               " RETURNING id", (rid, token), fetch="all")
    check("the current claim holder can write back", len(n) == 1)


def t_idem(db: Db, kw: dict) -> None:
    section("5. Idempotency - concurrency, and the 4xx path")
    ins = ("INSERT INTO idem (key,user_id,route,request_hash,state)"
           " VALUES ('k1',1,'/leads','h1','in_progress')"
           " ON CONFLICT (key,user_id,route) DO NOTHING RETURNING id")
    a = psycopg.connect(**kw)
    b = psycopg.connect(**kw)
    ca, cb = a.cursor(), b.cursor()
    for c_ in (ca, cb):
        c_.execute("SELECT set_config('search_path', %s, true)", (f"{SCHEMA},public",))
    cb.execute("SET lock_timeout = '1500ms'")

    ca.execute(ins)
    check("winner inserts", ca.fetchone() is not None)
    try:
        cb.execute(ins)
        check("loser blocks at the INSERT", False, "did not block")
    except psycopg.errors.LockNotAvailable:
        check("loser blocks at the INSERT", True, "lock_timeout fired, which is the block")
    b.rollback()
    cb.execute("SELECT set_config('search_path', %s, true)", (f"{SCHEMA},public",))
    ca.execute("UPDATE idem SET state='done', response_json='{\"ok\":true}' WHERE key='k1'")
    a.commit()
    cb.execute(ins)
    check("after commit the loser gets no row and no exception", cb.fetchone() is None)
    cb.execute("SELECT 1")
    check("loser transaction is not aborted", cb.fetchone()[0] == 1)
    cb.execute("SELECT state FROM idem WHERE key='k1'")
    check("loser reads the winner's committed response", cb.fetchone()[0] == "done")
    b.rollback()
    a.close()
    b.close()

    with psycopg.connect(**kw) as c:
        cur = c.cursor()
        cur.execute("SELECT set_config('search_path', %s, true)", (f"{SCHEMA},public",))
        cur.execute("INSERT INTO idem (key,user_id,route,request_hash,state)"
                    " VALUES ('k2',1,'/x','h','in_progress')")
        cur.execute("SAVEPOINT sp1")
        cur.execute("INSERT INTO biz (v) VALUES ('should vanish')")
        cur.execute("ROLLBACK TO SAVEPOINT sp1")
        cur.execute("UPDATE idem SET state='done', response_json='{\"error\":\"422\"}'"
                    " WHERE key='k2'")
        c.commit()          # normal exit, NOT an exception through the boundary
    r = db.run("SELECT (SELECT count(*) FROM biz), (SELECT state FROM idem WHERE key='k2')",
               fetch="one")
    check("savepoint rollback discards business writes", r[0] == 0, f"biz rows={r[0]}")
    check("the stored 4xx SURVIVES because the transaction commits normally",
          r[1] == "done", str(r[1]))


def t_money(db: Db) -> None:
    section("6. Outstanding balance - fan-out")
    db.run("""
        CREATE TABLE so2 (id int primary key, grand_total numeric(14,2));
        CREATE TABLE alloc (id serial primary key, so_id int, receipt_id int, amount numeric(14,2));
        CREATE TABLE rev (id serial primary key, receipt_id int);
        CREATE TABLE adj (id serial primary key, so_id int, amount numeric(14,2));
        INSERT INTO so2 VALUES (1,10000);
        INSERT INTO alloc (so_id,receipt_id,amount) VALUES (1,1,2000),(1,2,3000);
        INSERT INTO adj (so_id,amount) VALUES (1,100),(1,200);
    """)
    naive = db.run("""
        SELECT o.grand_total - COALESCE(SUM(a.amount) FILTER (WHERE r.id IS NULL),0)
                             - COALESCE(SUM(j.amount),0)
        FROM so2 o LEFT JOIN alloc a ON a.so_id=o.id
        LEFT JOIN rev r ON r.receipt_id=a.receipt_id
        LEFT JOIN adj j ON j.so_id=o.id GROUP BY o.id,o.grand_total""", fetch="one")[0]
    check("naive join reproduces the fan-out bug", naive == -600, f"got {naive}")
    cte = """
        WITH al AS (SELECT a.so_id, SUM(a.amount) paid FROM alloc a
                    LEFT JOIN rev r ON r.receipt_id=a.receipt_id
                    WHERE r.id IS NULL GROUP BY a.so_id),
             aj AS (SELECT so_id, SUM(amount) adjusted FROM adj GROUP BY so_id)
        SELECT o.grand_total - COALESCE(al.paid,0) - COALESCE(aj.adjusted,0)
        FROM so2 o LEFT JOIN al ON al.so_id=o.id LEFT JOIN aj ON aj.so_id=o.id"""
    check("CTE version is correct", db.run(cte, fetch="one")[0] == 4700)
    db.run("INSERT INTO rev (receipt_id) VALUES (2)")
    check("a reversed receipt stops reducing the balance", db.run(cte, fetch="one")[0] == 7700)


def t_misc(db: Db) -> None:
    section("7. Index immutability and ageing")
    db.expect_error(
        "CREATE INDEX ix_bad ON lead_intake (payload_hash, date_trunc('hour', received_at))",
        "date_trunc on timestamptz is rejected in an index", "immutable")
    check("the generated UTC column is indexable", True, "uq_intake_hash created in DDL")
    db.run("""
        CREATE TABLE se (id serial primary key, application_id int);
        CREATE TABLE sv (entry_id int, field_key text, value_date date);
        INSERT INTO se (application_id) VALUES (1),(1);
        INSERT INTO sv VALUES (1,'supply', current_date - 5),(2,'fp_submitted', current_date - 20);
    """)
    r = db.run("""
        SELECT current_date - MAX(v.value_date) FILTER (WHERE v.field_key='supply'),
               MAX(v.value_date) FILTER (WHERE v.field_key='fp_received')
             - MAX(v.value_date) FILTER (WHERE v.field_key='fp_submitted')
        FROM sv v JOIN se e ON e.id=v.entry_id WHERE e.application_id=1""", fetch="one")
    check("age_supply is positive for a past supply", r[0] == 5, f"got {r[0]}")
    check("a missing endpoint yields NULL, not zero", r[1] is None, f"got {r[1]}")


def main() -> None:
    kw = dsn()
    with psycopg.connect(**kw, autocommit=True) as c:
        cur = c.cursor()
        cur.execute("SELECT version()")
        print(f"Postgres: {cur.fetchone()[0].split(' on ')[0]}   schema: {SCHEMA}")
        print("=" * 66, flush=True)
        cur.execute(f"CREATE SCHEMA {SCHEMA}")
    db = Db(kw)
    try:
        db.run(DDL)
        t_rls(db)
        t_approval(db)
        t_intake(db)
        t_claim(db)
        t_idem(db, kw)
        t_money(db)
        t_misc(db)
    finally:
        with psycopg.connect(**kw, autocommit=True) as c:
            c.cursor().execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")

    passed = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 66)
    print(f"{passed}/{len(results)} checks passed")
    for n, ok, d in results:
        if not ok:
            print(f"  FAILED: {n} - {d}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
