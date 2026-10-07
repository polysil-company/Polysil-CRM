# RBAC — roles, permissions and policy design

> **Status:** DRAFT. **Freezes with the schema.**
> Source of truth for `role`, `role_permission` seed data **and** the generated test matrix. Both read this file — changing it changes both.
> Corrects the four policy defects found in an early review (`docs/BASELINE.md` §4.1).

---

## 1. The four corrections

| # | Defect | Fix |
|---|---|---|
| 1 | INSERT policies checked the action but not the row | **Every mutation carries an action check and a row-scope check**, with a partner branch so the portal works (§5.2) |
| 2 | Empty `user_territory` meant company-wide, so removing someone's last territory silently *broadened* access | **`role_permission.scope` is explicit.** `global` is a declared value, never an absence (§3) |
| 3 | Functional roles sit outside the line hierarchy, but the `app_user` CHECK requires every staff user to have an `org_unit_id` | **Functional roles attach to HQ org units** (§4). They stay in the tree; their reach comes from `scope`, not from descent |
| 4 | Permissive policies OR together, so an unconditional grant beside a narrower one widened access | **Every permissive branch is guarded by the scope it serves**, making them mutually exclusive (§5.1) |

---

## 2. Roles

Sixteen. Six in the line hierarchy, six functional, three portal, one board.

### Line hierarchy — position in `org_closure` determines reach

| # | Code | Name | Level |
|---|---|---|---|
| 1 | `field_officer` | Field Officer / Employee | 1 |
| 2 | `district_manager` | District Manager | 2 |
| 3 | `state_manager` | State Manager | 3 |
| 4 | `regional_manager` | Regional Manager | 4 |
| 5 | `admin_sales` | Admin-Sales Co-ordinator | 5 |
| 6 | `md_ceo` | MD / CEO | 5 |

### Functional — outside the line, reach from `scope`

| # | Code | Name | Scope |
|---|---|---|---|
| 7 | `account_manager` | Account Manager | global |
| 8 | `dispatch_manager` | Dispatch Manager | global |
| 9 | `qc_manager` | QC / QA Manager | global |
| 10 | `state_coordinator` | State Co-ordinator | **territory**, via `user_territory` |
| 11 | `marketing` | Marketing | global |
| 12 | `support` | Support | global |

### Portal — reach from `partner_closure`

| # | Code | Name |
|---|---|---|
| 13 | `distributor` | Distributor |
| 14 | `dealer` | Dealer |
| 15 | `sub_dealer` | Sub-dealer |

### Observer

| # | Code | Name |
|---|---|---|
| 16 | `board` | Board of Directors — view-only, global |

### Principals — not people, not in the matrix, never assignable

| Code | Who | Holds |
|---|---|---|
| `system` | the worker (migration 005) | no matrix rows; its reach is explicit `app_is_system()` branches |
| `intake` | the public lead form, "Website and QR" (migration 015, FS-003a) | leads view, create, edit and partners view, all global. Its claim is set only by `deps.intake_session`, after a WhatsApp code matched, and the route returns only an inquiry number. It has no password and no mobile, and a trigger refuses both, so it cannot sign in |

Neither is in the parsed matrix below, in `ASSIGNABLE_ROLES`, or reconciled by the seed.

Neither is administered either. `GET /users` never lists them, and every `/users/{id}` action refuses them (`422`, field `id`); a handover cannot name one as `to_user_id`. The intake account is also never a lead assignee: `authz_user_assignable()` and `staff_directory()` leave it out, although its role holds leads edit. Its trigger refuses a password, a mobile, a role or type change, deletion, deactivation and a move of office.

> **Agent is not a role.** Dropped by ADR-030; `Requirements.md` REQ-1109 is void. A salesperson is a `field_officer`.

---

## 3. Scope vocabulary

`role_permission.scope` is an explicit enum. **There is no implicit scope and no "absence means everything".**

| Scope | Rows visible | Held by |
|---|---|---|
| `own` | rows the user owns or created | Field Officer |
| `org_subtree` | rows whose `owner_org_unit_id` is in the user's org subtree | District / State / Regional Manager |
| `territory` | rows whose `territory_id` is under a territory in `user_territory` | State Co-ordinator |
| `partner_subtree` | rows whose `partner_id` is in the user's partner subtree | Distributor, Dealer, Sub-dealer |
| `global` | all rows, subject to the permission check | Admin, MD/CEO, Board, functional managers |

**District, state and region are no longer separate scopes.** They were descriptive labels for one mechanism — the closure table already determines depth from where the user sits. Collapsing them to `org_subtree` removes a distinction the policies could not act on and were getting wrong.

`user_territory` is used **only** by the `territory` scope. It never grants access on its own, and an empty `user_territory` for a `territory`-scoped user means they see nothing — correct and explicit, rather than the previous behaviour where emptiness silently meant everything.

---

## 4. Functional roles and the org-unit contradiction

ADR-030 places Account, Dispatch and QC Managers outside the sales line. The `app_user` CHECK requires every staff user to have an `org_unit_id`.

**Resolution: HQ org units.** Seed org units under the root for each function:

```
root (Polysil HQ)                        ← admin_sales, md_ceo, board
 ├── hq_accounts                          ← account_manager
 ├── hq_dispatch                          ← dispatch_manager
 ├── hq_quality                           ← qc_manager
 ├── hq_marketing                         ← marketing
 ├── hq_support                           ← support
 ├── hq_subsidy                           ← state_coordinator
 └── Regional Manager …                   ← the sales line
```

They stay in the tree, so task assignment (ADR-034), audit attribution and reporting all work unchanged. **Their reach comes from `scope`, not from closure descent** — an HQ node has no sales descendants, so a closure-only policy would return nothing. The `global` permissive policy in §5.1 is what serves them.

State Co-ordinators sit at `hq_subsidy` with `scope = territory` and rows in `user_territory`. Their access comes from the territory permissive branch (§5.1), not from closure descent — `hq_subsidy` has no sales descendants.

The `app_user` CHECK is unchanged.

---

## 5. Policy design

### 5.1 Every permissive branch is guarded by the scope it serves

PostgreSQL combines **permissive** policies with `OR` and **restrictive** policies with `AND`. The earlier draft got this wrong in a way worth stating plainly, because the mistake is easy to repeat:

> An *unconditional* staff-subtree grant sitting beside an `own`-record grant does not narrow anything. The two OR together, so a Field Officer with `V:own` could still read every lead in their org unit. **Adding a narrower policy never narrows.**

**The fix: each permissive branch tests the scope it implements.** Because `scope` is a single value per (role, module), **exactly one branch can ever be true** — so OR-ing them is safe by construction rather than by hope.

**Every helper call is a scalar subselect**, `(SELECT app_scope('leads'))`, never bare. A bare STABLE call with constant arguments is evaluated per row; the subselect is what makes Postgres hoist it to an InitPlan and evaluate it once per statement (CLAUDE.md rule 8, ADR-021). An earlier version of this section wrote all of them bare and FS-002 copied the form (ISS-056). The generator in `api/authz/policy_sql.py` emits the wrapped form and `tests/db/test_policy_drift_005.py` checks every live policy for a bare call.

```sql
-- PERMISSIVE: mutually exclusive by construction
CREATE POLICY lead_sel_own ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id())
);

CREATE POLICY lead_sel_org ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (
    SELECT descendant_id FROM org_closure
    WHERE ancestor_id = (SELECT app_current_org_unit())
  )
);

CREATE POLICY lead_sel_territory ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (
    SELECT tc.descendant_id FROM territory_closure tc
    JOIN user_territory ut ON ut.territory_id = tc.ancestor_id
    WHERE ut.user_id = (SELECT app_current_user_id())
  )
);

CREATE POLICY lead_sel_partner ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (
    SELECT descendant_id FROM partner_closure
    WHERE ancestor_id = (SELECT app_current_partner())
  )
);

CREATE POLICY lead_sel_global ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'global'
);

-- RESTRICTIVE: permission and soft delete only
CREATE POLICY lead_res_perm ON lead AS RESTRICTIVE FOR SELECT USING (
  (SELECT app_has_permission('leads', 'view'))
);

CREATE POLICY lead_res_deleted ON lead AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('leads', 'delete'))
);
```

**There is no restrictive territory policy.** The earlier draft had one, and it blocked every org-scoped manager with no `user_territory` rows — which is all of them. Territory scoping is a *permissive branch* for the roles that use it, not a restriction on everyone.

### 5.2 Mutations: action-specific permission, scope-checked rows

Each action checks **its own** permission. The earlier draft reused `create` on UPDATE, which would have denied an Account Manager who may approve an order but never create one.

```sql
CREATE POLICY lead_ins ON lead FOR INSERT WITH CHECK (
     ((SELECT app_scope('leads')) = 'global')
  OR ((SELECT app_scope('leads')) = 'own'
      AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
      AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure
                                WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
      AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc
                           JOIN user_territory ut ON ut.territory_id = tc.ancestor_id
                           WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
      AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure
                                  WHERE ancestor_id = (SELECT app_current_partner())))
);

CREATE POLICY lead_ins_perm ON lead AS RESTRICTIVE FOR INSERT
  WITH CHECK ((SELECT app_has_permission('leads', 'create')));

CREATE POLICY lead_upd ON lead FOR UPDATE
  USING      ( /* the five SELECT branches: may I see this row?          */ )
  WITH CHECK ( /* the five INSERT branches: may the result still be mine? */ );

CREATE POLICY lead_upd_perm ON lead AS RESTRICTIVE FOR UPDATE
  USING      ((SELECT app_has_permission('leads', 'edit')))
  WITH CHECK ((SELECT app_has_permission('leads', 'edit')));

CREATE POLICY lead_del ON lead FOR DELETE
  USING (/* the five SELECT branches */);

CREATE POLICY lead_del_perm ON lead AS RESTRICTIVE FOR DELETE
  USING ((SELECT app_has_permission('leads', 'delete')));
```

### 5.2a Approval is a separate, narrow path

`lead_upd_perm` requires `edit`. **Account and Dispatch Managers hold only `approve` on orders**, so under that policy alone they could not record a decision — and widening it to let approvers UPDATE freely would let them change prices.

**Approvers do not update the business row. They update their own approval step.**

**And nobody creates approval steps directly.** There is deliberately **no INSERT policy** on `approval_step` — a user who could insert steps could fabricate an approval chain. `create_approval_request(doc_type, entity_id, requested_by, roles[])` is a `SECURITY DEFINER` function and the only way in. Validation surfaced this: the first version had no INSERT path at all, and the test could not construct a case.

> **Ownership matters for this to work.** The application must connect as a **non-owner** role, so RLS applies to it while definer functions (owned by a privileged role) bypass it. `approval_step` is therefore `ENABLE`d but **not `FORCE`d** — a table owner cannot escape `FORCE` even with `row_security = off`, which would break the definer path.
>
> On the current development box `appuser` owns everything and cannot create roles, so the "a user cannot insert a step" half is **not provable there**. It is enforced by the absence of an INSERT policy plus a non-owner app role, and it needs re-checking on the VPS where roles can be separated.

`doc_type` lives on `approval_request`, not on `approval_step`, so the policy resolves it through `request_id`. Referencing it directly does not compile — verified: `42703: column "doc_type" does not exist`.

```sql
CREATE POLICY step_upd ON approval_step FOR UPDATE
  USING      (approver_role_id = (SELECT app_current_role())
              AND decision IS NULL)                      -- not yet decided
  WITH CHECK (decision IN ('approve','reject')
              AND approver_user_id = (SELECT app_current_user_id()));

CREATE POLICY step_upd_perm ON approval_step AS RESTRICTIVE FOR UPDATE
  USING (EXISTS (SELECT 1 FROM approval_request r
                  WHERE r.id = approval_step.request_id
                    AND app_has_permission(module_of(r.doc_type), 'approve')))
  WITH CHECK (EXISTS (SELECT 1 FROM approval_request r
                       WHERE r.id = approval_step.request_id
                         AND app_has_permission(module_of(r.doc_type), 'approve')));
```

### 5.2b Advancing the document — every guard, stated

The first version checked only that no step had a NULL decision. **Verified failing on two inputs:** a chain containing one `approve` and one `reject` advanced the order to `approved`, and a request with **no steps at all** did the same. Both are now impossible.

```sql
CREATE FUNCTION advance_approval(p_request_id uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $fn$
DECLARE
  v_req      approval_request%ROWTYPE;
  v_total    int;
  v_approved int;
  v_rejected int;
BEGIN
  SELECT * INTO v_req FROM approval_request WHERE id = p_request_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'approval_request % not found', p_request_id;
  END IF;

  -- 1. the request itself must still be open
  IF v_req.status <> 'pending' THEN
    RETURN v_req.status;                       -- already decided, idempotent no-op
  END IF;

  SELECT count(*),
         count(*) FILTER (WHERE decision = 'approve'),
         count(*) FILTER (WHERE decision = 'reject')
    INTO v_total, v_approved, v_rejected
    FROM approval_step WHERE request_id = p_request_id;

  -- 2. a chain with no steps approves nothing
  IF v_total = 0 THEN
    RAISE EXCEPTION 'approval_request % has no steps', p_request_id;
  END IF;

  -- 3. any rejection terminates the chain
  IF v_rejected > 0 THEN
    UPDATE approval_request SET status = 'rejected', decided_at = now()
     WHERE id = p_request_id;
    PERFORM set_document_status(v_req.doc_type, v_req.entity_id, 'rejected');
    RETURN 'rejected';
  END IF;

  -- 4. still waiting on someone
  IF v_approved < v_total THEN
    RETURN 'pending';
  END IF;

  -- 5. every step approved, and only now
  UPDATE approval_request SET status = 'approved', decided_at = now()
   WHERE id = p_request_id;
  PERFORM set_document_status(v_req.doc_type, v_req.entity_id, 'approved');
  RETURN 'approved';
END $fn$;
```

`set_document_status` is the only thing that touches the business row, and it changes **`status` and nothing else** — never a price, a quantity or a discount:

```sql
CREATE FUNCTION set_document_status(p_doc_type text, p_entity_id uuid, p_status text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $fn$
BEGIN
  CASE p_doc_type
    WHEN 'sales_order' THEN
      UPDATE sales_order SET status = p_status
       WHERE id = p_entity_id AND status IN ('submitted','pending_approval');
    WHEN 'quotation' THEN
      UPDATE quotation SET status = p_status
       WHERE id = p_entity_id AND status = 'sent';
    -- complaints are not on the engine (ADR-042); this arm is historical
    WHEN 'complaint' THEN
      UPDATE complaint SET status = p_status
       WHERE id = p_entity_id AND status = 'under_review';
    ELSE RAISE EXCEPTION 'unknown doc_type %', p_doc_type;
  END CASE;
END $fn$;
```

The `AND status IN (...)` guard on each branch means an already-dispatched order cannot be walked backwards by a late approval arriving out of order.

### 5.2c One entry point, and the actor is never a parameter

The first version took `p_actor` and ran `SECURITY DEFINER`. **Verified as a privilege escalation:** setting claims for a user with no approval permission and passing `p_actor = 5` recorded user 5 as the approver and advanced the order. A definer function that trusts a caller-supplied identity has no security at all — it bypasses the very policies meant to check it.

**`record_decision` is the only function the application may call.** It derives the actor from the verified claim, and re-checks everything a policy would:

```sql
CREATE FUNCTION record_decision(p_step_id uuid, p_decision text, p_remark text)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $fn$
DECLARE
  v_actor uuid := app_current_user_id();      -- from the claim, never a parameter
  v_step  approval_step%ROWTYPE;
  v_req   approval_request%ROWTYPE;
BEGIN
  IF v_actor IS NULL THEN
    RAISE EXCEPTION 'no_authenticated_actor' USING ERRCODE = '28000';
  END IF;
  IF p_decision NOT IN ('approve','reject') THEN
    RAISE EXCEPTION 'invalid_decision';
  END IF;

  SELECT * INTO v_step FROM approval_step WHERE id = p_step_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'step_not_found'; END IF;
  SELECT * INTO v_req FROM approval_request WHERE id = v_step.request_id;

  -- the definer bypasses RLS, so every check a policy would make is made here
  IF v_step.decision IS NOT NULL THEN
    RAISE EXCEPTION 'step_already_decided';
  END IF;
  IF v_step.approver_role_id <> (SELECT role_id FROM app_user WHERE id = v_actor) THEN
    RAISE EXCEPTION 'not_your_step' USING ERRCODE = '42501';
  END IF;
  IF NOT app_has_permission(module_of(v_req.doc_type), 'approve') THEN
    RAISE EXCEPTION 'no_approve_permission' USING ERRCODE = '42501';
  END IF;
  IF v_req.requested_by = v_actor THEN
    RAISE EXCEPTION 'self_approval_not_permitted' USING ERRCODE = '42501';
  END IF;
  IF EXISTS (SELECT 1 FROM approval_step
              WHERE request_id = v_step.request_id AND seq < v_step.seq
                AND decision IS NULL) THEN
    RAISE EXCEPTION 'earlier_step_undecided';
  END IF;
  -- scope: the actor must be able to see the document they are deciding on
  IF NOT document_in_scope(v_req.doc_type, v_req.entity_id, v_actor) THEN
    RAISE EXCEPTION 'document_out_of_scope' USING ERRCODE = '42501';
  END IF;

  UPDATE approval_step
     SET decision = p_decision, approver_user_id = v_actor,
         remark = p_remark, decided_at = now()
   WHERE id = p_step_id;

  RETURN advance_approval(v_step.request_id);
END $fn$;
```

**Grants say the rest.** `advance_approval` and `apply_approval_outcome` are internal — reachable only from `record_decision`, never from the application:

```sql
REVOKE ALL ON FUNCTION advance_approval, apply_approval_outcome FROM PUBLIC, app_role;
GRANT EXECUTE ON FUNCTION record_decision, create_approval_request TO app_role;
```

**Negative tests run under a non-owner role**, because an owner bypasses the grants that make this work at all. That cannot be proven on a box where the app user owns everything.

### 5.2d Approval outcomes map to each document's own lifecycle

The first version passed `'approved'` / `'rejected'` straight through to the document. **Verified failing:** `sales_order.status` has no `rejected` and `quotation.status` has no `approved`. PostgreSQL returned `22P02` against the real enums. It only appeared to work because the validator used unrestricted `text` columns.

**Approval outcome and document lifecycle are different vocabularies.** The mapping is per document, and for one of them approval changes no status at all:

| Document | approve | reject |
|---|---|---|
| `sales_order` | `submitted` → **`approved`** | `submitted` → **`draft`** — back to the raiser (ADR-031) |
| `quotation` | **no status change** — approval gates the *send action* | `draft` → stays `draft`, the request is what carries the rejection |
| `complaint` | not on the engine: ADR-042. `complaint_check()` moves `submitted` → **`under_qc`** | a return moves `submitted` → **`draft`** (FS-015) |

The quotation row is the one worth pausing on. What gets approved there is a **discount above threshold**, not the document — so approval does not move the quotation, it unblocks sending it. `POST /quotations/{id}/send` checks there is no pending approval request; that is the gate.

```sql
CREATE FUNCTION apply_approval_outcome(p_doc_type text, p_entity_id uuid, p_outcome text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $fn$
BEGIN
  CASE p_doc_type
    WHEN 'sales_order' THEN
      UPDATE sales_order
         SET status = CASE p_outcome WHEN 'approve' THEN 'approved'::order_status
                                     ELSE 'draft'::order_status END
       WHERE id = p_entity_id AND status = 'submitted';
    WHEN 'quotation' THEN
      NULL;                       -- deliberate: approval gates sending, not state
    -- complaints are not on the engine (ADR-042); this arm is historical
    WHEN 'complaint' THEN
      UPDATE complaint
         SET status = CASE p_outcome WHEN 'approve' THEN 'under_qc'::complaint_status
                                     ELSE 'draft'::complaint_status END
       WHERE id = p_entity_id AND status = 'under_review';
    ELSE RAISE EXCEPTION 'unknown doc_type %', p_doc_type;
  END CASE;
END $fn$;
```

The `WHERE status = ...` guard on each branch means an already-dispatched order cannot be walked backwards by a late approval arriving out of order.

**Every branch is cast to the real enum type**, so a value that does not exist in that document's lifecycle fails at the database rather than passing a text column. The validator now builds these columns as enums for exactly that reason — the previous version's `text` columns are what let this ship.

### 5.2e The rules the step policy enforces, and the ones the service must

| Rule | Enforced by |
|---|---|
| Only the assigned role may decide | `step_upd` USING |
| A step is decided once | `decision IS NULL` in USING |
| The decision is `approve` or `reject`, nothing else | `step_upd` WITH CHECK |
| The decider records themselves as the actor | `step_upd` WITH CHECK |
| The role holds `approve` on that document's module | `step_upd_perm`, resolved through `request_id` |
| **No self-approval** | `record_decision()`, from the claim |
| **Steps decide in sequence** | `record_decision()` |
| Actor is in scope for the document | `record_decision()` calls `document_in_scope()` — a definer bypasses RLS, so the check is explicit |
| **The actor is who they say they are** | `app_current_user_id()`, never a parameter |

Self-approval and sequencing moved from "service-layer, to be written" into `record_decision()`, a definer function — they need the requester and the ordering, which a row policy cannot see cheaply, but they are too important to leave to application discipline. Both are validated.

### 5.2f Tested behaviour

| | |
|---|---|
| An Account Manager **can** approve an order | holds `approve`; the step policy admits them |
| An Account Manager **cannot** change `grand_total` | no `edit`; the definer function touches only `status` |
| A chain with any rejection ends **rejected**, never approved | guard 3 |
| A request with **no steps** raises, and approves nothing | guard 2 |
| A partly-decided chain stays **pending** | guard 4 |
| Calling twice is a no-op | guard 1 |
| A dispatched order is not walked back by a late approval | `set_document_status` status guard |

This is why `approve` is a distinct action rather than a flavour of `edit`. Collapsing them would hand every approver a price-editing capability.

**The partner branch on INSERT is what lets a dealer raise a lead.** The earlier draft supported only global and org scope, so the portal's own documented action would have failed.

**`USING` and `WITH CHECK` are both required on UPDATE.** `USING` alone lets a user edit a row they can see into a state they could not have created — reassigning a lead out of their own subtree, for instance.

These branch sets repeat across ~20 tables, so they are **generated from this file into migration 017**, not hand-written per table. Writing five branches twenty times by hand is how one gets missed.

### 5.3 Helper functions

```sql
CREATE FUNCTION app_current_user_id() RETURNS uuid
LANGUAGE sql STABLE AS 'SELECT nullif(current_setting(''app.current_user_id'', true), '''')::uuid';

CREATE FUNCTION app_current_org_unit() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT org_unit_id FROM app_user WHERE id = (SELECT app_current_user_id())';

CREATE FUNCTION app_current_partner() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT partner_id FROM app_user WHERE id = (SELECT app_current_user_id())';

CREATE FUNCTION app_has_permission(p_module text, p_action text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT EXISTS (SELECT 1 FROM role_permission rp
                  JOIN app_user u ON u.role_id = rp.role_id
                  WHERE u.id = (SELECT app_current_user_id())
                    AND rp.module = p_module AND rp.action = p_action)';

CREATE FUNCTION app_current_role() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT role_id FROM app_user WHERE id = (SELECT app_current_user_id())';

CREATE FUNCTION app_scope(p_module text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER AS
  'SELECT rp.scope FROM role_permission rp
   JOIN app_user u ON u.role_id = rp.role_id
   WHERE u.id = (SELECT app_current_user_id())
     AND rp.module = p_module AND rp.action = ''view'' LIMIT 1';
```

All `STABLE`, and every call site wraps them in a scalar subselect, so Postgres hoists them to an InitPlan and evaluates once per statement rather than once per row.

**Required indexes:** `role_permission(role_id, module, action)` · `app_user(id) INCLUDE (role_id, org_unit_id, partner_id)` · `org_closure(ancestor_id)` · `partner_closure(ancestor_id)` · `territory_closure(ancestor_id)` · `user_territory(user_id)`.

### 5.4 The four cases the earlier draft got wrong

Kept as the regression list. Each is a named test in `tests/rbac/`.

| Case | Was | Now |
|---|---|---|
| Two Field Officers in one org unit | each saw the other's leads despite `V:own` | `own` branch matches `owner_user_id` only |
| State Co-ordinator at `hq_subsidy` | no permissive branch matched — saw nothing | `territory` branch grants via `user_territory` |
| State Manager with no `user_territory` | a restrictive territory policy blocked valid org access | no restrictive territory policy exists |
| Dealer creates a lead | INSERT had no partner branch — failed | partner branch added |
| State Co-ordinator seeded `V:org` | org subtree is empty at `hq_subsidy` — still no access | seeded `V:territory`; **test uses the seeded role, never an overridden scope** |
| Account Manager approves an order | UPDATE required `edit`, which they lack | approval writes `approval_step` under `approve`; a definer function moves status only (§5.2a) |
| `record_decision` took `p_actor` | **privilege escalation** — a caller with no permission passed another user's id and the order approved | actor comes from `app_current_user_id()`; every policy check repeated inside (§5.2b) |
| Outcome written straight to the document | **`22P02`** — `sales_order` has no `rejected`, `quotation` has no `approved` | outcomes map to each document's own lifecycle, cast to real enums (§5.2c) |
| Step policy referenced `doc_type` | **did not compile** — `42703: column "doc_type" does not exist`; it is on `approval_request` | resolved through `request_id` (§5.2a) |
| `advance_approval` guarded only on NULL decisions | **a reject-containing chain approved the order; so did a chain with no steps at all** | five explicit guards (§5.2b) |

### 5.5 Reports — materialized views do not inherit RLS

> **Live form, 4 Oct (ADR-047, FS-024).** Reports today are live aggregates, not materialized views. Their three rules: the module's scope predicate on every ScopeSpec table the query reads, with RLS beneath (six hand-policy tables are RLS-only, ISS-111); one exception by design: `order_paid_at()` (FS-026 rule 11) tells anyone who can see an order the day it was paid in full, a day and not an amount, so a salesperson without `payments.view` still sees their sales under payment mode; a figure without its module is null, never 0; and a cross-office leakage test per report and per export. The materialized-view form below applies when one is introduced.

Reading a materialized view returns stored rows; it does **not** re-run the source query under the reader's policies. Without this every report is a company-wide aggregate readable by anyone who can reach it.

```sql
CREATE MATERIALIZED VIEW mv_lead_conversion AS
SELECT owner_org_unit_id, territory_id, period, /* aggregates */
FROM lead GROUP BY 1, 2, 3;

REVOKE ALL ON mv_lead_conversion FROM PUBLIC, app_role;

CREATE VIEW rpt_lead_conversion WITH (security_barrier) AS
SELECT * FROM mv_lead_conversion m
WHERE app_has_permission('reports', 'view')
  AND ( app_scope('reports') = 'global'
     OR (app_scope('reports') = 'org_subtree'
         AND m.owner_org_unit_id IN (SELECT descendant_id FROM org_closure
                                     WHERE ancestor_id = (SELECT app_current_org_unit())))
     OR (app_scope('reports') = 'territory'
         AND m.territory_id IN (SELECT tc.descendant_id FROM territory_closure tc
                                JOIN user_territory ut ON ut.territory_id = tc.ancestor_id
                                WHERE ut.user_id = (SELECT app_current_user_id()))));

GRANT SELECT ON rpt_lead_conversion TO app_role;
```

Three rules per report: the aggregate keeps its scope dimensions, `REVOKE` on the MV and `GRANT` on the view only, and **a cross-district leakage test for the report and its export**. Exports bypass the UI, not the database, and they are the easy thing to forget.

---

## 6. The matrix

`view` carries a scope: `own` · `org` (org subtree) · `territory` · `partner` · `global`. Create, edit, approve and delete inherit the view scope but check **their own** permission. Blank means no permission.

### 6.1 Line hierarchy

| Module | field_officer | district_manager | state_manager | regional_manager | admin_sales | md_ceo |
|---|---|---|---|---|---|---|
| leads | V:own CE | V:org CE | V:org CED | V:org A | V:global CEAD | V:global CEAD |
| quotations | V:own CE | V:org CEA | V:org CEAD | V:org A | V:global CEAD | V:global CEAD |
| sales_orders | V:own CE | V:org CEA | V:org CEAD | V:org A | V:global CEAD | V:global CEAD |
| dispatch | V:own | V:org | V:org | V:org | V:global CE | V:global CE |
| complaints | V:own CE | V:org CEA | V:org CEAD | V:org A | V:global CEAD | V:global CEAD |
| payments | | V:org | V:org | V:org | V:global CEAD | V:global CEAD |
| subsidy | V:own CE | V:org CE | V:org CE | V:org | V:global CEAD | V:global CEAD |
| schemes | V:global | V:global | V:global | V:global | V:global CEAD | V:global CEAD |
| products | V:global | V:global | V:global | V:global | V:global CEAD | V:global CEAD |
| pricing | V:global | V:global | V:global | V:global | V:global CEAD | V:global CEAD |
| partners | V:org | V:org CE | V:org CE | V:org | V:global CEAD | V:global CEAD |
| marketing_material | V:global C | V:global CA | V:global CA | V:global A | V:global CEAD | V:global CEAD |
| rewards | V:own | V:org | V:org | V:org | V:global CEAD | V:global CEAD |
| tasks | V:own CE | V:org CE | V:org CE | V:org CE | V:global CEAD | V:global CEAD |
| reports | V:own | V:org | V:org | V:org | V:global | V:global |
| chat | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE |
| users | | V:org | V:org | V:org | V:global CEAD | V:global CEAD |
| masters | | | | | V:global CEAD | V:global CEAD |
| tracking | V:own CE | V:org CE | V:org CE | V:org CE | V:global CE | V:global CE |
| stock | V:global | V:global | V:global | V:global | V:global CE | V:global CE |
| targets | V:own | V:org C | V:org C | V:org C | V:global C | V:global C |

*V = view · C = create · E = edit · A = approve · D = delete*

### 6.2 Functional

| Module | account_manager | dispatch_manager | qc_manager | state_coordinator | marketing | support |
|---|---|---|---|---|---|---|
| leads | V:global | | | **V:territory** | V:global CE | V:global |
| quotations | V:global | | | **V:territory** | | V:global |
| sales_orders | V:global A | V:global A | | | | V:global |
| dispatch | V:global | V:global CEA | | | | V:global |
| complaints | V:global | | V:global CEA | | | V:global CE |
| payments | V:global CEA | | | | | |
| subsidy | V:global | | | **V:territory CE** | | |
| marketing_material | | | | | V:global CEAD | |
| campaigns | | | | | V:global CEAD | |
| reports | V:global | V:global | V:global | **V:territory** | V:global | V:global |
| users | V:global | V:global | | V:global | V:global | V:global |
| tasks | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE |
| chat | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE | V:own CE |
| stock | V:global | V:global C | V:global | V:global | V:global | V:global |

State Co-ordinators own subsidy stage entry (ADR-030), scoped by `user_territory`.

> **Whoever can see a lead, quotation or order sees the people on it.** Every role that views a document module views `users` at a scope that covers the people named on those documents: the line managers over their org subtree, the functional roles company-wide. Before this, the row was blank for them, and every list showed the owner as unassigned. The `users` spec has no territory branch, so State Co-ordinators read people company-wide (GAP-134). Write access (`C`, `E`, `D`) on `users` stays with the administrators.

> **Their scope is `territory`, never `org`.** They sit at `hq_subsidy`, which has no sales descendants, so an org-subtree seed would give them access to nothing at all. This was wrong in the previous revision — a global find-and-replace collapsing `V:state` into `V:org` caught these four rows along with the line-manager ones.
>
> **The RBAC test fixture must use the seeded role as it stands, never override its scope.** A test that sets `scope` itself would have passed against the broken seed, which is exactly how this survived a revision.

### 6.3 Portal

Scope is `partner_subtree` throughout, served by the partner permissive branch (§5.1) on both SELECT and INSERT. The one exception is `tasks` (FS-037, ADR-034 as amended): own scope, the dealer user's own tasks, assigned by staff while the `tasks_for_dealers` setting is on; edit means completing, enforced by `task_partner_guard()`. A distributor sees its dealers and their sub-dealers; a sub-dealer sees only itself.

| Module | distributor | dealer | sub_dealer |
|---|---|---|---|
| leads | V CE | V CE | V CE |
| quotations | V | V | V |
| sales_orders | V CE | V CE | V CE |
| dispatch | V | V | V |
| complaints | V CE | V CE | V CE |
| tasks | V:own E | V:own E | V:own E |
| payments | V | V | V |
| partners | V CE | V CE | |
| products | V | V | V |
| pricing | V *(own tier only)* | V *(own tier only)* | V *(own tier only)* |
| schemes | V *(applicable only)* | V | V |
| marketing_material | V C | V C | V C |
| rewards | V + redeem | V + redeem | V + redeem |
| reports | V *(own subtree)* | V | V |

> **Pricing visibility across tiers is a hard rule, not a UI choice.** A sub-dealer must never resolve dealer pricing, and a dealer must never see distributor pricing. Enforced by a restrictive policy on `price_list` keyed to the user's own `partner_type`.

> **`products` is a portal row because a picker cannot work without one.** The catalogue is the same 1,092 rows for everyone and carries no commercial figure: the rate lives on the price list, which the tier rule above narrows. Without this row a dealer could read the table through RLS and still be refused at the endpoint, which is the disagreement ADR-039's dual enforcement exists to make impossible (FS-010 rule 12).

### 6.4 Board

`view` on everything at `global`. No create, edit, approve or delete anywhere.

**Except:** `tracking`, `stock`. Staff locations are not board information (FS-021, GAP-195); company stock is an operational figure the board reads in reports (FS-023).

---

## 7. Generated tests

`tests/db/test_matrix_005.py` enumerates the cells from this file, through `api/domain/authz.py:parse_matrix()`, the same parser that seeds `role_permission`. Never hand-edited; a cell changed here changes the seed and the assertions together.

**16 roles × 22 modules × 5 actions = 1,760 assertions** (ISS-031: an earlier count of 18 modules and 1,440 missed `campaigns` and `stock`; FS-021 added `tracking`, FS-025 `targets`), and the negatives matter more than the positives:

| Class | Assertion |
|---|---|
| Positive | the permission listed here is granted |
| **Negative** | every permission *not* listed is denied |
| **Scope** | a District Manager reads none of another district's rows |
| **Cross-tree** | a partner user reads no staff-only row, and no other partner's rows |
| **Mutation scope** | a user cannot insert or update a row into a scope they do not hold |
| **Tier** | a sub-dealer cannot read dealer pricing |
| **Report** | every report and every export is scope-filtered |
| **Soft delete** | deleted rows are invisible without `delete` permission |

The mutation-scope class is the one that would have caught defect 1, and it did not exist before this document.

---

## 8. Open

| # | Question | Default |
|---|---|---|
| 1 | Does a Distributor approve anything beyond a Dealer? | same as Dealer |
| 2 | Admin-Sales Co-ordinator below MD/CEO, or alongside? | alongside, both level 5 |
| 3 | Board of Directors — view-all, or a restricted set? | view-all |
| 4 | Marketing and Support permissions | inferred from the BRD; **needs client confirmation** |
| 5 | Can one user hold two roles? | one — `role_id` on `app_user` |

Items 4 and 5 are the ones worth pushing. The rest are single config rows.
