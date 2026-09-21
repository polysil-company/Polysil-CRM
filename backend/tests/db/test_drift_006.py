"""The definer bodies migration 006 pasted are what the generator emits today
(ISS-071). The policy drift suite covers policies; these cover the two function
bodies the generator also owns: the parent guard and the visibility guard inside
lead_visible(). Whitespace is normalised; anything else is drift."""

from __future__ import annotations

from api.authz.modules import SPECS
from api.authz.policy_sql import guard_sql, parent_guard_ddl
from tests.db.migration_grants import _load

LEADS = SPECS["leads"]


def _norm(s: str) -> str:
    return " ".join(s.split())


def test_the_parent_guard_snapshot_matches_the_generator() -> None:
    m = _load("006_leads")
    assert m is not None
    assert [_norm(x) for x in parent_guard_ddl(LEADS)] == [_norm(x) for x in m.LEAD_PARENT_GUARD]


def test_lead_visible_embeds_the_generated_guard() -> None:
    m = _load("006_leads")
    assert m is not None
    body = next(f for f in m.FUNCTIONS if "FUNCTION lead_visible" in f)
    assert _norm(guard_sql(LEADS)) in _norm(body)
