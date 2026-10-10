"""Delete one migration-013 mechanism at a time on the dev database, run the test
that claims to prove it, restore the original, and report whether the test went red.

Each mutation is a text edit of the live function (pg_get_functiondef) or a grant;
the original is restored in a finally, whatever happens.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv("infra/.env")
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
T = "tests/db/test_migration_013.py"  # run from the repo root

FUNCTION_MUTATIONS = [
    ("Accounts may escalate onto a line step", "approval_refusal(uuid)",
     "IF v_step_line AND v_my_line AND v_my_level > v_step_level THEN",
     "IF v_my_level > v_step_level THEN",
     "test_accounts_and_dispatch_never_decide_a_line_step"),
    ("no self-approval check", "approval_refusal(uuid)",
     "RETURN 'self_approval';", "NULL;",
     "test_submit_numbers_the_order_and_builds_the_chain_from_the_owner"),
    ("steps need not decide in sequence", "record_decision(uuid,text,text)",
     "RAISE EXCEPTION 'earlier_step_undecided' USING ERRCODE = 'APREU';", "NULL;",
     "test_steps_decide_in_order_and_accounts_must_say_why"),
    ("the owner's level is ignored", "approval_chain(text,numeric,uuid,integer)",
     "IF v_levels[i] > p_owner_level THEN", "IF true THEN",
     "test_the_chain_by_band_and_owner_level"),
    ("close short writes no lines", "order_close_short_lines()",
     "UPDATE order_line l",
     "PERFORM 1; -- UPDATE order_line l\n    RETURN NULL; UPDATE order_line l",
     "test_close_short_writes_the_lines_and_a_direct_write_cannot"),
    ("the line trigger admits qty_short at any depth", "refuse_submitted_order_line_edit()",
     "pg_trigger_depth() >= 2", "true",
     "test_close_short_writes_the_lines_and_a_direct_write_cannot"),
    ("dispatch ignores the open quantity", "dispatch_record(uuid,jsonb)",
     "IF r.qty > (SELECT", "IF false AND r.qty > (SELECT",
     "test_dispatch_counts_open_quantity_and_derives_the_status"),
    ("the lead timeline does not filter orders",
     "lead_timeline(uuid,timestamp with time zone,uuid,integer)",
     "AND (entity_type <> 'sales_order' OR order_visible(entity_id))", "",
     "test_the_lead_timeline_hides_a_direct_sale_order_from_the_leads_dealer"),
    ("a decision ignores whether the approver sees the order", "approval_refusal(uuid)",
     "IF NOT order_visible(v_req.entity_id) OR NOT app_has_permission", "IF NOT app_has_permission",
     "test_a_district_manager_elsewhere_can_neither_decide_nor_see_the_step"),
]


# The races (tests/api/test_order_concurrency.py): each deletes every lock that
# serialises one race, so the second call no longer waits or no longer re-reads.
RACE_TESTS = "tests/api/test_order_concurrency.py"
RACE_MUTATIONS = [
    ("dispatch does not lock the order or its lines", "dispatch_record(uuid,jsonb)",
     [("WHERE id = p_order_id FOR UPDATE;", "WHERE id = p_order_id;"),
      ("sales_order_id = p_order_id ORDER BY id FOR UPDATE;", "sales_order_id = p_order_id;")],
     "test_two_dispatches_racing_one_line_never_ship_more_than_was_ordered"),
    ("a decision does not lock the order or its request", "record_decision(uuid,text,text)",
     [("WHERE id = v_entity FOR UPDATE;", "WHERE id = v_entity;"),
      ("WHERE id = v_request FOR UPDATE;", "WHERE id = v_request;")],
     "test_a_decision_that_loses_to_a_cancel_is_refused_as_closed"),
    ("the claim does not lock the quotations", "order_quotations_claim(uuid,uuid[])",
     [("ORDER BY id FOR UPDATE LOOP", "ORDER BY id LOOP")],
     "test_two_orders_claiming_one_quotation_leave_it_on_one"),
]


def run(test: str, path: str = T) -> bool:
    """True when the test passed."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        path, "-k", test], capture_output=True, text=True)
    return r.returncode == 0


async def main() -> int:
    c = await asyncpg.connect(DSN)
    survived = 0
    for label, sig, old, new, test in FUNCTION_MUTATIONS:
        original = await c.fetchval("SELECT pg_get_functiondef(CAST($1 AS regprocedure))", sig)
        assert original.count(old) >= 1, f"{label}: anchor not found"
        try:
            await c.execute(original.replace(old, new, 1))
            passed = run(test)
        finally:
            await c.execute(original)
        survived += passed
        print(f"{'SURVIVED' if passed else 'caught  '}  {label}")
    # the column grant: give app_role UPDATE on status, then take it back
    try:
        await c.execute("GRANT UPDATE (status) ON sales_order TO app_role")
        passed = run("test_app_role_cannot_write_the_status_by_update_or_by_insert")
    finally:
        await c.execute("REVOKE UPDATE (status) ON sales_order FROM app_role")
    survived += passed
    print(f"{'SURVIVED' if passed else 'caught  '}  app_role may update status")
    for label, sig, edits, test in RACE_MUTATIONS:
        original = await c.fetchval("SELECT pg_get_functiondef(CAST($1 AS regprocedure))", sig)
        mutated = original
        for old, new in edits:
            assert mutated.count(old) == 1, f"{label}: anchor {old!r} not unique"
            mutated = mutated.replace(old, new)
        try:
            await c.execute(mutated)
            passed = run(test, RACE_TESTS)
        finally:
            await c.execute(original)
        survived += passed
        print(f"{'SURVIVED' if passed else 'caught  '}  {label}")
    await c.close()
    total = len(FUNCTION_MUTATIONS) + 1 + len(RACE_MUTATIONS)
    print(f"{total - survived} of {total} caught")
    return survived


sys.exit(asyncio.run(main()))
