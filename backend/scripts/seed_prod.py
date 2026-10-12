#!/usr/bin/env python3
"""Seed a production database: the roles, the permission matrix limited to the
released modules, the approval stand-ins, the states, and the first administrator.

    python scripts/seed_prod.py                      # in the tools container
    python scripts/seed_prod.py --modules leads,quotations,...   # widen later

**The release scope is the permission rows.** A module a role holds no row for is
refused by the API and hidden by the frontend's navigation. Widening the scope is
a rerun with more modules, no deploy. The rows come from the same RBAC.md matrix
the demo seed uses (`generate_permission_seed.load_grants`), filtered.

**No demo data, no known password.** The administrator's email and password come
from ADMIN_EMAIL and ADMIN_PASSWORD (infra/.env.prod); the account changes its
password at first sign-in unless ADMIN_MUST_CHANGE_PASSWORD=false. Idempotent: a rerun reconciles the permission rows,
leaves the thresholds an administrator has edited alone, and never resets an
existing administrator's password.
"""

# ruff: noqa: E501  (SQL inline)

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from argon2 import PasswordHasher

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_permission_seed import load_grants  # noqa: E402

# Go-live scope: leads, quotations, sales orders with approvals and
# dispatch, tasks, users and roles, offices, territories and dealers, products and
# price lists, staff messages. The dashboard and the bell need no module.
RELEASED = ("leads", "quotations", "sales_orders", "dispatch", "tasks", "users", "masters",
            "partners", "products", "pricing", "chat")

# seed_demo's sixteen roles, verbatim: the matrix names them
ROLES: list[tuple[str, str, int, bool, bool]] = [
    ("field_officer", "Field Officer", 1, False, False),
    ("district_manager", "District Manager", 2, False, False),
    ("state_manager", "State Manager", 3, False, False),
    ("regional_manager", "Regional Manager", 4, False, False),
    ("admin_sales", "Admin-Sales Co-ordinator", 5, False, False),
    ("md_ceo", "MD / CEO", 5, False, False),
    ("account_manager", "Account Manager", 5, True, False),
    ("dispatch_manager", "Dispatch Manager", 5, True, False),
    ("qc_manager", "QC / QA Manager", 5, True, False),
    ("state_coordinator", "State Co-ordinator", 3, True, False),
    ("marketing", "Marketing", 3, True, False),
    ("support", "Support", 2, True, False),
    ("distributor", "Distributor", 3, False, True),
    ("dealer", "Dealer", 2, False, True),
    ("sub_dealer", "Sub-dealer", 1, False, True),
    ("board", "Board of Directors", 5, True, False),
]

# the states the client sells in, with the codes lead and document numbers carry;
# districts and talukas the administrator adds
STATES = [("Gujarat", "GJ"), ("Rajasthan", "RJ"), ("Chhattisgarh", "CG"),
          ("Uttar Pradesh", "UP"), ("Madhya Pradesh", "MP"), ("Maharashtra", "MH"),
          ("Andhra Pradesh", "AP")]

ROOT_ORG_UNIT_ID = "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea"   # migration 006's head office


def grants(modules: set[str]) -> dict[str, dict[str, tuple[str, list[str]]]]:
    out: dict[str, dict[str, tuple[str, list[str]]]] = {}
    for g in load_grants():
        if g.module not in modules:
            continue
        mods = out.setdefault(g.role, {})
        _scope, actions = mods.setdefault(g.module, (g.scope, []))
        actions.append(g.action)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--modules", default=",".join(RELEASED),
                        help="comma-separated modules to grant (default: the go-live scope)")
    args = parser.parse_args(argv)
    modules = {m.strip() for m in args.modules.split(",") if m.strip()}
    known = {g.module for g in load_grants()}
    if modules - known:
        raise SystemExit(f"unknown modules: {', '.join(sorted(modules - known))}")

    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        raise SystemExit("set ADMIN_EMAIL and ADMIN_PASSWORD (12 characters or more)")
    # ADMIN_MUST_CHANGE_PASSWORD=false keeps the given password (no change screen)
    must_change = os.environ.get("ADMIN_MUST_CHANGE_PASSWORD", "true").strip().lower() != "false"

    with psycopg.connect(host=os.environ.get("DB_HOST", "pgbouncer"),
                         port=int(os.environ.get("DB_PORT", "6432")),
                         user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                         dbname=os.environ["DB_NAME"]) as conn:
        cur = conn.cursor()
        for code, name, level, functional, portal in ROLES:
            cur.execute(
                "INSERT INTO role (code, name, level, is_functional, is_portal) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (code) DO UPDATE "
                "SET name = EXCLUDED.name, level = EXCLUDED.level",
                (code, name, level, functional, portal))

        matrix = grants(modules)
        cur.execute("SELECT id, code FROM role")
        role_ids = {code: rid for rid, code in cur.fetchall()}
        for code, rid in role_ids.items():
            declared: list[str] = []
            for module, (scope, actions) in matrix.get(code, {}).items():
                for action in actions:
                    cur.execute(
                        "INSERT INTO role_permission (role_id, module, action, scope) "
                        "VALUES (%s, %s, %s::permission_action, %s::permission_scope) "
                        "ON CONFLICT (role_id, module, action) DO UPDATE SET scope = EXCLUDED.scope",
                        (rid, module, action, scope))
                    declared.append(f"{module}:{action}")
            # outside the scope, or no longer declared: no row (RBAC.md 6, a blank cell)
            cur.execute("DELETE FROM role_permission WHERE role_id = %s "
                        "AND NOT (module || ':' || action::text = ANY(%s))", (rid, declared))
        cur.execute("SELECT assert_role_permission_invariants()")

        # the approval stand-ins, as seed_demo writes them; an edited row is left alone
        for doc, rows in (("sales_order", [("district_manager", "100000"), ("state_manager", "500000"),
                                           ("regional_manager", None)]),
                          ("quotation", [("field_officer", "5"), ("district_manager", "10"),
                                         ("state_manager", "15"), ("regional_manager", "20"),
                                         ("admin_sales", None)])):
            for role, amount in rows:
                cur.execute(
                    "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
                    "VALUES (%s, %s, NULL, %s) ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING",
                    (doc, role_ids[role], amount))

        for name, code in STATES:
            cur.execute("SELECT id FROM territory WHERE level = 'state' AND (code = %s OR name = %s)",
                        (code, name))
            if cur.fetchone() is None:
                cur.execute("INSERT INTO territory (name, level, code) VALUES (%s, 'state', %s)",
                            (name, code))

        cur.execute("SELECT 1 FROM app_user WHERE email = %s AND deleted_at IS NULL", (email,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, "
                "org_unit_id, must_change_password) VALUES ('staff', %s, %s, 'Administrator', "
                "%s, %s, %s)",
                (email, PasswordHasher().hash(password), role_ids["admin_sales"], ROOT_ORG_UNIT_ID,
                 must_change))
            print(f"  admin    {email} created" + ("; the password must be changed at first sign-in"
                                                   if must_change else ""))
        else:
            print(f"  admin    {email} exists; left as it is")
        conn.commit()
    granted = sum(len(a) for mods in matrix.values() for _, a in mods.values())
    print(f"  scope    {len(modules)} modules, {granted} permission rows: {', '.join(sorted(modules))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
