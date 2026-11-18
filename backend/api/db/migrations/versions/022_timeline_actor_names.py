"""022: the lead timeline names the actor of events written inside the database.

`approval.decided`, `order.approved`, `quotation.approval_requested` and the other
events a definer writes carry no `actor_name`, so the history read "Polysil asked
for a discount approval" (the frontend walk, 29 Sep). `lead_event_people()` now
also names the actors of this lead's events that carry no name, for staff
readers only: a dealer is never told who decided (question 15.14), and these are
mostly decider events.

Forward only: 021 is applied on staging.

Revision ID: 022_timeline_actor_names
Revises: 021_lead_extras
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "022_timeline_actor_names"
down_revision: str | None = "021_lead_extras"
branch_labels = None
depends_on = None


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_022", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"022: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"022: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _before() -> str:
    return next(f for f in _load("021_lead_extras").FUNCTIONS
                if f.startswith("CREATE FUNCTION lead_event_people("))


def _after() -> str:
    f = _before()
    f = _replace(f, "    )\n    SELECT u.id, u.full_name, false FROM app_user u\n     WHERE u.id IN (SELECT ref FROM refs WHERE k <> 'assigned_partner_id')\n",
                 "    ), actors AS (\n"
                 "        -- the actors of events written without a name, for staff only\n"
                 "        SELECT DISTINCT e.actor_id AS ref FROM activity_event e\n"
                 "         WHERE (SELECT app_current_partner()) IS NULL AND lead_visible(p_lead_id)\n"
                 "           AND e.actor_id IS NOT NULL AND NOT (e.payload ? 'actor_name')\n"
                 "           AND (e.lead_id = p_lead_id\n"
                 "                OR e.lead_id IN (SELECT l.id FROM lead l WHERE l.merged_into_id = p_lead_id))\n"
                 "    )\n"
                 "    SELECT u.id, u.full_name, false FROM app_user u\n"
                 "     WHERE u.id IN (SELECT ref FROM refs WHERE k <> 'assigned_partner_id')\n"
                 "        OR u.id IN (SELECT ref FROM actors)\n")
    return _replace(f, "CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ")


def upgrade() -> None:
    op.execute(_after())


def downgrade() -> None:
    op.execute(_replace(_before(), "CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION "))
