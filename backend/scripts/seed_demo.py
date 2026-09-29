#!/usr/bin/env python3
"""Seed the `demo` dataset: the sixteen roles, a small hierarchy, and users.

    python scripts/seed_demo.py

**Idempotent.** Run it as often as you like. Roles upsert by `code`, and the
seed-only trigger permits that precisely because it compares with
`IS DISTINCT FROM` - writing identical values is not a change.

The permission rows are the full 16 x 20 x 5 matrix, parsed from `RBAC.md`
section 6 by `scripts/generate_permission_seed.py` (FS-002 5.3). A blank cell is
the absence of a row, and rows this matrix no longer declares are removed. The
users and hierarchy are enough to sign in and render a navigation, which is what
unblocks the frontend track (GAP-015 - there is still no
staff-creation endpoint, so seeded users are the only way in).

**The passwords here are public.** They are in this file, in the repository, and
the script refuses to run outside a local environment for that reason.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import psycopg
from argon2 import PasswordHasher

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_permission_seed import load_grants  # noqa: E402

PUBLIC_DEFAULT = "polysil-demo-2026"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", PUBLIC_DEFAULT)


def guard_passwords(script: str) -> None:
    """Refuse to write a known password anywhere it could matter.

    The check is the password, not a file. It used to be `infra/.env` naming
    `ENVIRONMENT=local`, which the staging deploy satisfied by writing that file
    for itself with no `ENVIRONMENT` line in it: the gate was one line in a file
    the caller controls, and the caller was us (ISS-083). Its "no harm today, the
    box is loopback-only" note stopped being true the day the API got a domain.

    What actually matters is whether the password being written is the one
    published in this file. A generated password on a staging box is fine; the
    default anywhere but a laptop is not; production is never.
    """
    environment = os.environ.get("ENVIRONMENT") or env().get("ENVIRONMENT") or "local"
    if environment == "production":
        raise SystemExit(f"{script}: never against production.")
    if DEMO_PASSWORD == PUBLIC_DEFAULT and environment != "local":
        raise SystemExit(
            f"{script}: DEMO_PASSWORD is still the password published in this script and "
            f"ENVIRONMENT is {environment!r}. Set DEMO_PASSWORD to something generated "
            f"(infra/.env.staging) and run it again.")

# RBAC.md section 2. Sixteen: six in the line hierarchy, six functional, three
# portal, one board.
ROLES: list[tuple[str, str, int, bool, bool]] = [
    # code, name, level, is_functional, is_portal
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

# The full matrix, from RBAC.md section 6 through the same parser migration 005
# and the parity suite use. Before 005 this was a hand-written slice, and the
# cross-vendor round on FS-002 found two overgrants in it that a suite enumerating
# from the dict would have blessed. Every (role, module) carries `view` because the
# document does; assert_role_permission_invariants() checks it again at seed time.
def permissions() -> dict[str, dict[str, tuple[str, list[str]]]]:
    out: dict[str, dict[str, tuple[str, list[str]]]] = {}
    for g in load_grants():
        modules = out.setdefault(g.role, {})
        scope, actions = modules.setdefault(g.module, (g.scope, []))
        assert scope == g.scope, (g.role, g.module)
        actions.append(g.action)
    return out


PERMISSIONS = permissions()


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    e = env()
    guard_passwords("seed_demo")

    hasher = PasswordHasher()
    pw = hasher.hash(DEMO_PASSWORD)

    with psycopg.connect(
        host="127.0.0.1", port=6432, user=e["DB_USER"],
        password=e["DB_PASSWORD"], dbname=e["DB_NAME"],
    ) as conn:
        cur = conn.cursor()

        for code, name, level, functional, portal in ROLES:
            cur.execute(
                """
                INSERT INTO role (code, name, level, is_functional, is_portal)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                   SET name = EXCLUDED.name, level = EXCLUDED.level
                """,
                (code, name, level, functional, portal),
            )

        for role_code, modules in PERMISSIONS.items():
            cur.execute("SELECT id FROM role WHERE code = %s", (role_code,))
            role_id = cur.fetchone()[0]
            for module, (scope, actions) in modules.items():
                for action in actions:
                    cur.execute(
                        """
                        INSERT INTO role_permission (role_id, module, action, scope)
                        VALUES (%s, %s, %s::permission_action, %s::permission_scope)
                        ON CONFLICT (role_id, module, action)
                          DO UPDATE SET scope = EXCLUDED.scope
                        """,
                        (role_id, module, action, scope),
                    )
            # Reconcile: a row this dict no longer declares is removed. Upsert alone
            # left two overgrants in place across reseeds until the cross-vendor round
            # on FS-002 found them in the database. RBAC.md 6: a blank cell is the
            # absence of a row.
            declared = [f"{m}:{a}" for m, (_, acts) in modules.items() for a in acts]
            cur.execute(
                """
                DELETE FROM role_permission
                 WHERE role_id = %s
                   AND NOT (module || ':' || action::text = ANY(%s))
                """,
                (role_id, declared),
            )

        # The invariant the whole permission model assumes, asserted at seed time
        # rather than discovered when an UPDATE quietly affects nothing.
        cur.execute("SELECT assert_role_permission_invariants()")

        # The approval thresholds name roles, and roles are created here, not by a
        # migration. On a fresh database migration 013's seed finds no roles and
        # inserts nothing (ISS-098). Seed the same stand-ins (question 15.1,
        # GAP-122); an existing row, an admin's edit included, is left alone.
        cur.execute(
            """
            INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount)
            SELECT 'sales_order', r.id, NULL, v.amount
              FROM (VALUES ('district_manager', 100000.00::numeric),
                           ('state_manager', 500000.00), ('regional_manager', NULL)) v(code, amount)
              JOIN role r ON r.code = v.code
            ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING
            """
        )
        # FS-013: the discount each role may give on a quotation, in percent
        # (question 6.8, GAP-105). The officer's row is its own limit; Admin-Sales
        # tops the ladder, uncapped. Migration 017 inserts the same where roles exist.
        cur.execute(
            """
            INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount)
            SELECT 'quotation', r.id, NULL, v.pct
              FROM (VALUES ('field_officer', 5.00::numeric), ('district_manager', 10.00),
                           ('state_manager', 15.00), ('regional_manager', 20.00),
                           ('admin_sales', NULL)) v(code, pct)
              JOIN role r ON r.code = v.code
            ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING
            """
        )

        territories = _tree(
            cur, "territory",
            [("Gujarat", "state", None), ("Rajkot", "district", "Gujarat"),
             ("Gondal", "taluka", "Rajkot")],
        )
        # The state needs a code: the inquiry number is POL/<state code>/<FY>/<n>
        # (FS-003 rule 3), and a lead in a territory with no coded state ancestor is
        # refused. Set it here so a freshly seeded database can create leads.
        cur.execute("UPDATE territory SET code = 'GJ' WHERE id = %s AND code IS NULL",
                    (territories["Gujarat"],))
        orgs = _org_tree(cur, territories)

        cur.execute("SELECT id, code FROM role")
        role_ids = {code: rid for rid, code in cur.fetchall()}

        staff = [
            ("admin@polysil.in", "Admin Sales", "admin_sales", "HQ"),
            ("asha@polysil.in", "Asha Patel", "district_manager", "Rajkot District"),
            ("ravi@polysil.in", "Ravi Solanki", "field_officer", "Rajkot Field"),
        ]
        for email, full_name, role_code, org_name in staff:
            cur.execute(
                """
                INSERT INTO app_user (user_type, email, password_hash, full_name,
                                      role_id, org_unit_id)
                VALUES ('staff', %s, %s, %s, %s, %s)
                ON CONFLICT (email) WHERE deleted_at IS NULL
                  DO UPDATE SET password_hash = EXCLUDED.password_hash,
                                full_name = EXCLUDED.full_name,
                                role_id = EXCLUDED.role_id,
                                org_unit_id = EXCLUDED.org_unit_id,
                                is_active = true
                """,
                (email, pw, full_name, role_ids[role_code], orgs[org_name]),
            )

        # Stable ids, so a reseed is idempotent and so the dealer created here
        # carries the id that Bhavesh Shah's row has pointed at since before 004
        # existed. That is what lets fk_app_user_partner_id validate on a database
        # seeded before the table was created.
        distributor = uuid.uuid5(uuid.NAMESPACE_DNS, "polysil.demo.distributor")
        partner = uuid.uuid5(uuid.NAMESPACE_DNS, "polysil.demo.dealer")
        for pid, parent, ptype, code, name in (
            (distributor, None, "distributor", "DEMO-DIST", "Rajkot Agro Distributors"),
            (partner, distributor, "dealer", "DEMO-DLR", "Shah Irrigation, Rajkot"),
        ):
            cur.execute(
                """
                INSERT INTO channel_partner (id, parent_id, partner_type, code, name,
                                             territory_id, price_tier)
                VALUES (%s, %s, %s::partner_type, %s, %s, %s, %s::channel_tier)
                ON CONFLICT (id) DO UPDATE
                   SET parent_id = EXCLUDED.parent_id, name = EXCLUDED.name,
                       is_active = true, deleted_at = NULL
                """,
                (str(pid), str(parent) if parent else None, ptype, code, name,
                 territories["Rajkot"], ptype),
            )
        cur.execute(
            """
            INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id)
            VALUES ('partner_user', %s, %s, %s, %s)
            ON CONFLICT (mobile) WHERE deleted_at IS NULL
              DO UPDATE SET full_name = EXCLUDED.full_name,
                            role_id = EXCLUDED.role_id,
                            partner_id = EXCLUDED.partner_id,
                            is_active = true
            """,
            ("919876543210", "Bhavesh Shah", role_ids["dealer"], str(partner)),
        )

        # The seller's own GST registration. Migration 010 seeds one too, but by
        # selecting the Gujarat territory - which no migration creates, so on a
        # fresh database that INSERT matches zero rows and the default registration
        # the pricing endpoint resolves is permanently absent. Nothing errors; a
        # quotation just answers 404 forever. Seeded here as well, after the
        # territory exists, and idempotent on the number.
        cur.execute(
            """
            INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, is_default,
                                      effective_from)
            VALUES ('24AAAAA0000A1Z5', 'Polysil Irrigation Systems Limited', %s, true,
                    DATE '2026-04-01')
            ON CONFLICT (gstin) DO UPDATE
               SET state_territory_id = EXCLUDED.state_territory_id, is_active = true,
                   deleted_at = NULL
            """,
            (territories["Gujarat"],),
        )

        conn.commit()

        # The demo dealer now exists with the id Bhavesh's row has always carried, so
        # the constraint 004 added NOT VALID can be validated. In its own
        # transaction, after the seed's work is committed: an orphan that this seed
        # does not own must not take the roles, territories and users down with it.
        # It names the offending rows and exits non-zero instead.
        try:
            cur.execute("ALTER TABLE app_user VALIDATE CONSTRAINT fk_app_user_partner_id")
            conn.commit()
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback()
            cur.execute(
                "SELECT id, mobile, partner_id FROM app_user "
                "WHERE partner_id IS NOT NULL "
                "AND partner_id NOT IN (SELECT id FROM channel_partner)"
            )
            print("\n  fk_app_user_partner_id is still NOT VALID. These rows point at no partner:")
            for row in cur.fetchall():
                print(f"    app_user {row[0]}  mobile {row[1]}  partner_id {row[2]}")
            print("  Fix or delete them, then re-run the seed.")
            sys.exit(1)

    print("  seeded")
    print(f"    16 roles, {sum(len(a) for m in PERMISSIONS.values() for _, a in m.values())} "
          "permissions, 3 territories, 4 org units")
    print("\n  staff sign-in (POST /api/v1/auth/login):")
    for email, _, role_code, _ in staff:
        print(f"    {email:22} {role_code:18} password: {DEMO_PASSWORD}")
    print("\n  dealer sign-in (POST /api/v1/auth/otp/request then /otp/verify):")
    print("    919876543210           dealer")
    print("    the code is not sent anywhere yet - read it from notification_outbox:")
    print("      SELECT payload FROM notification_outbox ORDER BY created_at DESC LIMIT 1;")


def _tree(cur: psycopg.Cursor, table: str,
          rows: list[tuple[str, str, str | None]]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for name, level, parent in rows:
        cur.execute(f"SELECT id FROM {table} WHERE name = %s", (name,))
        found = cur.fetchone()
        if found:
            ids[name] = found[0]
            continue
        cur.execute(
            f"INSERT INTO {table} (name, level, parent_id) "
            "VALUES (%s, %s::territory_level, %s) RETURNING id",
            (name, level, ids.get(parent) if parent else None),
        )
        ids[name] = cur.fetchone()[0]
    return ids


# Migration 006's anchor: uuid5(DNS, "polysil.hq"), the one org root every migrated
# database carries. The seed's tree hangs under it, so the seed stands alone and the
# showcase (scripts/seed_showcase.py) shares the root (FS-006 5).
ROOT_ORG_UNIT_ID = "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea"


def _org_tree(cur: psycopg.Cursor, territories: dict[str, str]) -> dict[str, str]:
    rows = [
        ("Gujarat State", 3, "HQ", "Gujarat"),
        ("Rajkot District", 2, "Gujarat State", "Rajkot"),
        ("Rajkot Field", 1, "Rajkot District", "Gondal"),
    ]
    ids: dict[str, str] = {"HQ": ROOT_ORG_UNIT_ID}
    _fold_old_root(cur)
    for name, level, parent, territory in rows:
        cur.execute("SELECT id FROM org_unit WHERE name = %s", (name,))
        found = cur.fetchone()
        if found:
            ids[name] = found[0]
            continue
        cur.execute(
            "INSERT INTO org_unit (name, role_level, parent_id, territory_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (name, level, ids.get(parent) if parent else None,
             territories.get(territory) if territory else None),
        )
        ids[name] = cur.fetchone()[0]
    return ids


def _fold_old_root(cur: psycopg.Cursor) -> None:
    """Earlier seeds created their own root named "HQ". Everything anchored on it,
    soft-deleted rows included, moves to the anchor before the old row goes (an FK
    refuses otherwise, executed), so a rerun on a dirty database does not abort."""
    cur.execute("SELECT id FROM org_unit WHERE name = 'HQ' AND id <> %s", (ROOT_ORG_UNIT_ID,))
    old = [r[0] for r in cur.fetchall()]
    for old_id in old:
        cur.execute("UPDATE org_unit SET parent_id = %s WHERE parent_id = %s",
                    (ROOT_ORG_UNIT_ID, old_id))
        cur.execute("UPDATE app_user SET org_unit_id = %s WHERE org_unit_id = %s",
                    (ROOT_ORG_UNIT_ID, old_id))
        cur.execute("UPDATE lead SET owner_org_unit_id = %s WHERE owner_org_unit_id = %s",
                    (ROOT_ORG_UNIT_ID, old_id))
        cur.execute(
            "DELETE FROM org_unit ou WHERE ou.id = %s "
            "AND NOT EXISTS (SELECT 1 FROM org_unit c WHERE c.parent_id = ou.id) "
            "AND NOT EXISTS (SELECT 1 FROM app_user u WHERE u.org_unit_id = ou.id)",
            (old_id,))


if __name__ == "__main__":
    main()
