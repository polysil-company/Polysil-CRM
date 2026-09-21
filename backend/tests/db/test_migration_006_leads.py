"""Migration 006's lead schema: the tables, enums, constraints, seeds and RLS are
what FS-003 5 describes. The policies are covered by the drift and parity suites;
this covers the shape the generator does not emit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db


async def test_the_lead_enums_carry_their_values(db: AsyncSession) -> None:
    stages = (await db.execute(text(
        "SELECT enum_range(NULL::lead_stage)::text"))).scalar_one()
    for v in ("new", "contacted", "qualified", "quoted", "negotiation", "won",
              "lost", "merged", "dormant"):
        assert v in stages
    assert "merged" in stages, "the merge terminal stage (round 3 B-1)"


@pytest.mark.parametrize("table,cols", [
    ("lead", ("inquiry_no", "stage", "mis_system_id", "lead_source_id", "owner_user_id",
              "owner_org_unit_id", "assigned_partner_id", "lost_from_stage", "reopen_count",
              "merged_into_id", "external_id", "source_system")),
    ("lead_source", ("code", "quality", "is_active", "external_id")),
    ("mis_system", ("code", "is_active", "external_id")),
    ("won_lost_reason", ("kind", "code", "is_active", "external_id")),
    ("lead_score_rule", ("key", "value")),
    ("lead_duplicate_link", ("lead_a_id", "lead_b_id", "signal", "state", "resolved_by")),
    ("inquiry_counter", ("state_code", "financial_year", "last_value")),
])
async def test_the_tables_and_columns_exist(db: AsyncSession, table: str,
                                            cols: tuple[str, ...]) -> None:
    live = {r[0] for r in (await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table})).all()}
    assert live, f"{table} does not exist"
    assert set(cols) <= live, f"{table} missing {set(cols) - live}"


@pytest.mark.parametrize("name", [
    "ck_lead_lost_reason", "ck_lead_merged", "ck_lead_mobile_e164",
    "ck_lead_not_merged_into_self", "ck_lead_farmer_name_shape", "ck_lead_estimated_value",
])
async def test_the_lead_constraints_exist(db: AsyncSession, name: str) -> None:
    n = (await db.execute(text(
        "SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": name})).scalar_one()
    assert n == 1, name


async def test_the_mobile_check_accepts_e164_and_rejects_the_rest(db: AsyncSession) -> None:
    ok = (await db.execute(text("SELECT '+919876543210' ~ '^[+][1-9][0-9]{7,14}$'"))).scalar_one()
    bad = (await db.execute(text("SELECT '9876543210' ~ '^[+][1-9][0-9]{7,14}$'"))).scalar_one()
    assert ok is True and bad is False


async def test_the_merged_check_ties_the_pointer_to_the_stage(db: AsyncSession) -> None:
    """(merged_into_id IS NULL) = (stage <> 'merged'): both set or neither, so the
    one UPDATE merge cannot leave a half state (round 3 B-1)."""
    d = (await db.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_lead_merged'"))).scalar_one()
    assert "merged_into_id IS NULL" in d and "'merged'" in d


_SEEDED = {
    "lead_source": ("code", ["whatsapp", "website", "employee", "dealer", "campaign",
                             "agri_fair", "farmer_meeting", "qr_code", "form_link"]),
    "mis_system": ("code", ["drip", "mini_sprinkler", "sprinkler", "automation", "other"]),
    "won_lost_reason": ("code", ["price", "competitor", "no_response", "product_mismatch",
                                 "financing_not_approved", "out_of_area"]),
    "lead_score_rule": ("key", ["w_source", "w_value", "w_speed", "w_engagement", "value_cap",
                                "speed_fast_hours", "speed_slow_hours", "engagement_cap",
                                "threshold_hot", "threshold_warm"]),
}


@pytest.mark.parametrize("table", list(_SEEDED))
async def test_the_lookups_are_seeded(db: AsyncSession, table: str) -> None:
    # Every seeded code is present, once. Extra rows are allowed: the live drivers add
    # lookup items through the API and, by ADR-033, nothing removes them.
    col, codes = _SEEDED[table]
    got = (await db.execute(text(f"SELECT {col} FROM {table}"))).scalars().all()
    assert set(codes) <= set(got)
    assert len(got) == len(set(got))


async def test_scoring_keys_are_the_ones_the_function_reads(db: AsyncSession) -> None:
    keys = {r[0] for r in (await db.execute(text("SELECT key FROM lead_score_rule"))).all()}
    assert {"w_source", "w_value", "w_speed", "w_engagement", "value_cap",
            "speed_fast_hours", "speed_slow_hours", "engagement_cap",
            "threshold_hot", "threshold_warm"} == keys


@pytest.mark.parametrize("table", [
    "lead", "lead_source", "mis_system", "won_lost_reason", "lead_score_rule",
    "lead_duplicate_link",
])
async def test_rls_is_enabled(db: AsyncSession, table: str) -> None:
    on = (await db.execute(text(
        "SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": table})).scalar_one()
    assert on is True, f"{table} is not fail-closed"


async def test_the_inquiry_counter_is_owner_only(db: AsyncSession) -> None:
    """No grant to app_role at all: the definer function owns it, so a gap in the
    sequence cannot be caused by a direct write (FS-003 5)."""
    for verb in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        held = (await db.execute(text(
            "SELECT has_table_privilege('app_role', 'inquiry_counter', :v)"),
            {"v": verb})).scalar_one()
        assert held is False, verb


@pytest.mark.parametrize("name", [
    "ix_lead_name_trgm", "ix_lead_created_keyset", "ix_lead_org_stage",
    "ix_lead_territory_stage", "uq_lead_external", "ix_lead_dup_b",
    "ix_activity_event_lead",
])
async def test_the_hand_indexes_exist(db: AsyncSession, name: str) -> None:
    n = (await db.execute(text(
        "SELECT count(*) FROM pg_indexes WHERE indexname = :n"), {"n": name})).scalar_one()
    assert n == 1, name


async def test_the_masters_are_audited(db: AsyncSession) -> None:
    """Rule 23, cross-vendor B-9: a change to a lookup is in audit_log."""
    for table in ("lead_source", "mis_system", "won_lost_reason", "lead_score_rule",
                  "lead", "lead_duplicate_link"):
        n = (await db.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname = :t"),
            {"t": f"trg_{table}_audit"})).scalar_one()
        assert n == 1, f"{table} has no audit trigger"


# ── bootstrap: the root org-unit anchor (FS-003 rule 4, ISS-067) ─────────────

async def test_the_root_org_unit_anchor_is_seeded_once(db: AsyncSession) -> None:
    """Settings names the anchor and 006 seeds it, so a lead in a territory no sales
    unit covers routes to Polysil HQ rather than failing a foreign key."""
    from api.config import get_settings

    root = get_settings().root_org_unit_id
    assert root, "config must name the anchor"
    rows = (await db.execute(text(
        "SELECT name, role_level, territory_id FROM org_unit WHERE id = CAST(:r AS uuid)"),
        {"r": root})).all()
    assert len(rows) == 1
    assert rows[0].name == "Polysil HQ" and rows[0].role_level == 5 and rows[0].territory_id is None
