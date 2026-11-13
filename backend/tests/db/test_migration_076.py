"""Migration 076 (FS-064 5): the print block the render claim carries, executed.

What the client's sheet prints beside the figures is read by a definer at claim
time. These prove what it reads, that it cannot be called by anyone but the
claim, and that a block which raises costs one attempt instead of the queue.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import quotations as domain
from tests.db.conftest import Fixtures, make_staff
from tests.db.test_migration_012 import (
    SYSTEM_USER_ID,
    _as,
    _as_owner,
    _as_system,
    _lead,
    _line,
    _quotation,
    _refused,
)

pytestmark = [pytest.mark.db, pytest.mark.rls]

BLOCK = "quotation_print_block(uuid)"
VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"


def _migration(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _territory(db: AsyncSession, ids: Fixtures, level: str, name: str,
                     parent: str | None) -> str:
    return str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) "
        "VALUES (CAST(:l AS territory_level), :n, CAST(:p AS uuid)) RETURNING id"),
        {"l": level, "n": ids.unique(name), "p": parent})).scalar_one())


async def _chain(db: AsyncSession, ids: Fixtures) -> dict[str, str]:
    """A state with a district, a taluka and a village under it, of this test's own."""
    out: dict[str, str] = {}
    parent: str | None = None
    for level in ("state", "district", "taluka", "village"):
        parent = out[level] = await _territory(db, ids, level, level, parent)
    return out


async def _place(db: AsyncSession, lead: str, territory: str, village: str | None) -> None:
    await db.execute(text("UPDATE lead SET territory_id = CAST(:t AS uuid), village = :v "
                          "WHERE id = CAST(:l AS uuid)"), {"t": territory, "v": village, "l": lead})


async def _send(db: AsyncSession, q: str) -> None:
    """Draft to sent, the way test_migration_012's helper does it: the line goes in
    first, because the line trigger refuses a write under a sent parent."""
    await _line(db, q)
    await db.execute(text(
        "UPDATE quotation SET status = 'sent', sent_at = now(), valid_until = CURRENT_DATE + 45, "
        "share_token = :token, quote_no = :no, seller_legal_name = 'Polysil', "
        "seller_gstin_no = '24AAAAA0000A1Z5', seller_state_code = 'GJ', pdf_state = 'pending', "
        "pdf_next_attempt_at = now() - interval '1 day' WHERE id = CAST(:q AS uuid)"),
        {"token": domain.share_token(), "no": "QT/T/" + uuid.uuid4().hex[:8], "q": q})


async def _block(db: AsyncSession, q: str) -> Any:
    """The block as the claim calls it: the owner, under the system claim."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": SYSTEM_USER_ID})
    await _as_owner(db)
    return (await db.execute(text(f"SELECT {BLOCK.split('(')[0]}(CAST(:q AS uuid))"),
                             {"q": q})).scalar_one()


async def _claim_until(db: AsyncSession, mine: set[str]) -> Any:
    """The next claim that is one of this test's rows; a foreign row's lease is
    handed back, as test_migration_012 does."""
    for _ in range(40):
        doc = (await db.execute(text("SELECT quotation_render_claim(interval '5 minutes')"))
               ).scalar_one()
        if doc is None or str(doc["quotation"]["id"]) in mine:
            return doc
        await db.execute(text(
            "SELECT quotation_render_failed(CAST(:id AS uuid), CAST(:t AS uuid), 'test skip')"),
            {"id": str(doc["quotation"]["id"]), "t": str(doc["lease_token"])})
    raise AssertionError("none of this test's rows was ever claimed")


# ── what the block reads ─────────────────────────────────────────────────────

async def test_the_block_carries_the_quotations_dealer_the_chain_and_the_maker(
        db: AsyncSession, ids: Fixtures) -> None:
    chain = await _chain(db, ids)
    other_state = await _territory(db, ids, "state", "supply", None)
    maker = await make_staff(db, ids, email=f"maker-{uuid.uuid4().hex[:8]}@polysil.test")
    lead = await _lead(db, ids)
    # the free text disagrees with the village-level territory: the territory wins
    await _place(db, lead, chain["village"], "Typed By Hand")
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) "
                          "WHERE id = CAST(:l AS uuid)"), {"p": ids.distributor_id, "l": lead})
    await db.execute(text("UPDATE channel_partner SET contact_name = 'Bhavesh Shah', "
                          "mobile = '9876500000', is_active = false WHERE id = CAST(:p AS uuid)"),
                     {"p": ids.dealer_id})
    q = await _quotation(db, ids, lead)
    await db.execute(text(
        "UPDATE quotation SET partner_id = CAST(:p AS uuid), created_by = CAST(:u AS uuid), "
        "place_of_supply_state_id = CAST(:s AS uuid) WHERE id = CAST(:q AS uuid)"),
        {"p": ids.dealer_id, "u": maker, "s": other_state, "q": q})

    got = await _block(db, q)
    names = {r.id: r.name for r in (await db.execute(text(
        "SELECT CAST(id AS text) AS id, name FROM territory WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [*chain.values(), other_state]})).all()}
    dealer = (await db.execute(text("SELECT name FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                               {"p": ids.dealer_id})).scalar_one()
    full_name = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"), {"u": maker})).scalar_one()
    assert got == {
        "dealer_name": dealer, "dealer_contact": "Bhavesh Shah", "dealer_mobile": "9876500000",
        "village": names[chain["village"]], "taluka": names[chain["taluka"]],
        "district": names[chain["district"]], "state": names[chain["state"]],
        "supply_state": names[other_state], "mis_system": got["mis_system"],
        "made_by": full_name,
    }
    assert got["mis_system"] == (await db.execute(text(
        "SELECT name FROM mis_system WHERE code = 'drip'"))).scalar_one()
    assert "approved_by" not in got, "FS-012 rules 2 and 9: a partner never learns who approved"


@pytest.mark.parametrize(("level", "blank"), [
    ("taluka", ()), ("district", ("taluka",)), ("state", ("taluka", "district")),
])
async def test_a_lead_placed_above_the_village_prints_what_it_has(
        db: AsyncSession, ids: Fixtures, level: str, blank: tuple[str, ...]) -> None:
    chain = await _chain(db, ids)
    lead = await _lead(db, ids)
    await _place(db, lead, chain[level], "  Vadod ")
    q = await _quotation(db, ids, lead)
    got = await _block(db, q)
    assert got["village"] == "Vadod", "the lead's own text, trimmed, when no village territory"
    for name in ("taluka", "district"):
        assert (got[name] is None) == (name in blank), (level, name, got)
    assert got["state"] is not None
    assert got["dealer_name"] is None and got["dealer_mobile"] is None, "no dealer on the quotation"


async def test_a_blank_village_and_an_unknown_quotation_are_null(
        db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    await _place(db, lead, ids.territory_id, "   ")
    q = await _quotation(db, ids, lead)
    assert (await _block(db, q))["village"] is None
    assert await _block(db, str(uuid.uuid4())) is None


# ── who may call it ──────────────────────────────────────────────────────────

async def test_the_block_is_granted_to_nobody_and_guarded_on_the_system_principal(
        db: AsyncSession, ids: Fixtures) -> None:
    held = (await db.execute(text(
        "SELECT has_function_privilege('app_role', :s, 'EXECUTE'), "
        "has_function_privilege('app_anon', :s, 'EXECUTE'), "
        "has_function_privilege('public', :s, 'EXECUTE')"), {"s": BLOCK})).one()
    assert tuple(held) == (False, False, False)

    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead)
    staff = await make_staff(db, ids, email=f"caller-{uuid.uuid4().hex[:8]}@polysil.test")
    # the owner holds execute, so only the guard can refuse: with the guard deleted
    # this returns a block instead of raising
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(staff)})
    await _as_owner(db)
    message = await _refused(db, "SELECT quotation_print_block(CAST(:q AS uuid))", {"q": q},
                             "42501")
    assert "only the system principal renders" in message
    # and a signed-in caller cannot reach it at all
    await _as(db, staff)
    denied = await _refused(db, "SELECT quotation_print_block(CAST(:q AS uuid))", {"q": q},
                            "42501")
    assert "permission denied" in denied


# ── the claim ────────────────────────────────────────────────────────────────

async def test_the_claim_carries_the_block(db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    await _place(db, lead, ids.territory_id, "Vadod")
    q = await _quotation(db, ids, lead)
    await _send(db, q)
    await _as_system(db)
    doc = await _claim_until(db, {q})
    assert doc is not None and doc["print"]["village"] == "Vadod"
    assert "error" not in doc["print"]
    assert doc["attempt"] == 1 and len(doc["lines"]) == 1 and "subsidy" in doc


async def test_a_block_that_raises_costs_one_attempt_and_the_queue_moves_on(
        db: AsyncSession, ids: Fixtures) -> None:
    """Edge case 2. Without the sub-block the raise rolls the attempt charge back,
    the row stays first in the queue, and no later quotation ever renders."""
    lead = await _lead(db, ids)
    first = await _quotation(db, ids, lead)
    second = await _quotation(db, ids, lead)
    for q in (first, second):
        await _send(db, q)
    # this transaction's own body, gone with the rollback
    await db.execute(text(
        "CREATE OR REPLACE FUNCTION quotation_print_block(p_quotation uuid) RETURNS jsonb "
        "LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$ "
        "BEGIN RAISE EXCEPTION 'two talukas above one village'; END $fn$"))
    await _as_system(db)
    one = await _claim_until(db, {first, second})
    two = await _claim_until(db, {first, second})
    assert one is not None and two is not None
    assert {str(one["quotation"]["id"]), str(two["quotation"]["id"])} == {first, second}
    for doc in (one, two):
        assert doc["print"] == {"error": "two talukas above one village"}
        assert doc["attempt"] == 1 and len(doc["lines"]) == 1
    await _as_owner(db)
    rows = (await db.execute(text(
        "SELECT pdf_state, pdf_attempts, pdf_lease_token IS NOT NULL AS leased FROM quotation "
        "WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": [first, second]})).all()
    assert [tuple(r) for r in rows] == [("rendering", 1, True)] * 2, "lease and charge stand"


async def test_the_claims_body_holds_every_anchor_once(db: AsyncSession) -> None:
    """076 swaps three places and its downgrade swaps them back; 072's downgrade
    must still find its own line with 076 applied (edge case 20)."""
    body = str((await db.execute(text(
        "SELECT pg_get_functiondef('quotation_render_claim'::regproc)"))).scalar_one())
    m076, m072 = _migration("076_quotation_print_block"), _migration("072_subsidised_quotations")
    for _old, new in m076.SWAPS:
        assert body.count(new) == 1, new[:50]
    assert body.count(m072.CLAIM_NEW) == 1, "072's downgrade anchor"
    kept = (await db.execute(text(
        "SELECT has_function_privilege('app_role', 'quotation_render_claim(interval)', 'EXECUTE'), "
        "has_function_privilege('public', 'quotation_render_claim(interval)', 'EXECUTE')"))).one()
    assert tuple(kept) == (True, False), "CREATE OR REPLACE keeps the claim's grants"


class _FakeOp:
    """Alembic's `op`, as far as `_swap` uses it: read one body, execute one."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.executed: list[str] = []

    def get_bind(self) -> _FakeOp:
        return self

    def execute(self, statement: object) -> _FakeOp:
        if not str(statement).startswith("SELECT pg_get_functiondef"):
            self.executed.append(str(statement))
            self.body = str(statement)
        return self

    def scalar_one(self) -> str:
        return self.body


async def test_the_swap_reverses_exactly_and_refuses_a_body_that_drifted(
        db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """The downgrade restores the claim byte for byte, and an anchor that is
    missing or doubled stops the migration instead of writing a half-swapped
    function (code review F-7)."""
    m076 = _migration("076_quotation_print_block")
    live = str((await db.execute(text(
        "SELECT pg_get_functiondef('quotation_render_claim'::regproc)"))).scalar_one())
    down = tuple((new, old) for old, new in reversed(m076.SWAPS))

    fake = _FakeOp(live)
    monkeypatch.setattr(m076, "op", fake)
    m076._swap(down)
    before = fake.body
    assert before != live and "v_print" not in before and "quotation_print_block" not in before
    m076._swap(m076.SWAPS)
    assert fake.body == live, "up after down is the live body"

    lines_anchor = m076.SWAPS[2][0]
    assert before.count(lines_anchor) == 1
    for drifted in (before.replace("v_token uuid;", "v_token uuid ;"),     # an anchor gone
                    before.replace(lines_anchor, lines_anchor + "\n" + lines_anchor)):  # doubled
        fake = _FakeOp(drifted)
        monkeypatch.setattr(m076, "op", fake)
        with pytest.raises(RuntimeError, match=r"anchor found [02] times"):
            m076._swap(m076.SWAPS)
        assert fake.executed == [], "nothing is written when an anchor is off"
