"""activity_event: which reference column each entity type must carry.

FS-002 5.7. Reading an event is reading its entity, and a policy cannot join a
polymorphic reference, so each mapped entity type resolves through one
denormalised column. Migration 005 carries the CHECK and the read policy as
literals, the way it carries the generated policies, and the drift test asserts
both literals equal what this module emits. A new module extends `ENTITY_REFS`,
adds its table to `LIVE_TABLES` in the migration that creates it, regenerates,
and pastes.

`app_user` maps to nothing: FS-001 writes sign-in and sign-out with all three
reference columns null, and those rows are read by their own user through
entity_id, or by a manager holding users.view over the user's row.
"""

from __future__ import annotations

# entity_type -> the reference column that carries its scope
ENTITY_REFS: dict[str, str] = {
    "lead": "lead_id",
    "channel_partner": "partner_id",
    "customer": "customer_id",
    # FS-005 5: a quotation event always carries its lead, so the lead timeline
    # reads it; its visibility resolves through the quotation (ENTITY_BY_ID).
    "quotation": "lead_id",
}

# entity_type -> the table whose policies decide visibility. Only tables that
# exist: an arm on a missing table fails to parse, so an entity type is added
# here by the migration that creates its table, and falls to the principal
# until then.
LIVE_TABLES: dict[str, str] = {
    "channel_partner": "channel_partner",
    "lead": "lead",
}

# Entity types with no denormalised reference column: the row is visible when the
# entity itself is, resolved through entity_id. Both tables are readable by every
# authenticated caller (org_unit_sel, territory_sel), so a closed office's event
# stays visible. Kept out of ENTITY_REFS on purpose: activity_event carries no
# org_unit_id or territory_id column, and a CHECK requiring one would not compile
# (FS-006 5, plan review round 2 B-5).
# FS-011: an order event may carry no lead (a direct order, a consolidated one),
# so sales_order resolves through entity_id and is not in ENTITY_REFS; approval
# and dispatch events are written as sales_order events with their own kind.
# FS-003a: a QR code's events resolve through the code's own policies.
# FS-014: tasks and meeting minutes, never in ENTITY_REFS: a task may carry no lead,
# and the CHECK would demand one (plan review B-4).
ENTITY_BY_ID: tuple[str, ...] = ("org_unit", "territory", "quotation", "sales_order",
                                 "lead_qr_code", "task", "meeting_minutes")

# A type in both LIVE_TABLES and ENTITY_BY_ID would emit two `WHEN` arms, the
# first through its reference column's table and the second dead, and PostgreSQL
# accepts that silently (FS-005 edge case 23). ENTITY_REFS and ENTITY_BY_ID may
# overlap: the CHECK and the arm are different facts.
if set(LIVE_TABLES) & set(ENTITY_BY_ID):
    raise RuntimeError(f"an entity type is in both LIVE_TABLES and ENTITY_BY_ID: "
                       f"{set(LIVE_TABLES) & set(ENTITY_BY_ID)}")


def check_sql() -> str:
    """The CHECK expression: every mapped entity type carries its reference."""
    return " AND ".join(f"(entity_type <> '{t}' OR {c} IS NOT NULL)"
                        for t, c in ENTITY_REFS.items())


def read_policy_sql() -> str:
    """The SELECT policy body. A row is visible when its entity is: EXISTS on the
    entity's own table runs under the caller's policies. Unmapped types fall to
    the system principal."""
    arms = ["WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) "
            "OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)"]
    for entity_type, table in LIVE_TABLES.items():
        arms.append(f"WHEN '{entity_type}' THEN EXISTS "
                    f"(SELECT 1 FROM {table} c WHERE c.id = {ENTITY_REFS[entity_type]})")
    for entity_type in ENTITY_BY_ID:
        arms.append(f"WHEN '{entity_type}' THEN EXISTS "
                    f"(SELECT 1 FROM {entity_type} c WHERE c.id = entity_id)")
    return ("CASE entity_type\n    " + "\n    ".join(arms)
            + "\n    ELSE (SELECT app_is_system())\n  END")


def policy_sql() -> str:
    """The statement as it appears in migration 005's HAND_POLICIES."""
    return ("CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  "
            + read_policy_sql() + "\n)")
