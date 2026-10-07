"""Grants and hand-written policies, unioned across every migration that declares them.

Each migration owns the tables it creates, but a later one adds to an earlier one:
006 grants `idempotency_record` UPDATE (which 005 created) and re-creates
`activity_event_sel`. Reading `mig005` alone then makes three tests red the day 006
lands (plan review round 2 B-5, cross-vendor R-2). Two rules make the union correct:

  * grants union as verb SETS per table, so 006 adding UPDATE to a table 005 also
    grants does not drop 005's verbs;
  * policies are last-declaration-wins keyed on (table, policy name), so a policy a
    later migration re-creates (006 rewrites `activity_event_sel`) is counted once,
    with the later text.

A module named here that does not exist yet is skipped, so this reads as 005 alone
until 006 is written.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

_VERSIONS = Path(__file__).resolve().parents[2] / "api/db/migrations/versions"

# In apply order. Each may define GRANTS: dict[str, str] and HAND_POLICIES:
# list[tuple[str, str]]. Add a migration here when it grants or hand-writes a policy.
_MODULE_NAMES = ("005_authorization", "006_leads", "007_administration",
                 "008_message_delivery", "009_subsidy_masters",
                 "010_products_and_pricing", "012_quotations",
                 "013_orders_approvals_dispatch", "015_public_lead_capture",
                 "017_quotation_discount_approval",
                 "018_tasks_planner", "019_complaints", "020_complaint_fixes",
                 "021_lead_extras", "022_timeline_actor_names", "023_notifications",
                 "024_messages", "025_subsidy_applications", "026_complaint_remedies",
                 "033_schemes", "036_rewards", "037_dealer_commission", "038_marketing_material",
                 "039_subsidy_follow_ups",
                 "030_field_tracking", "031_payments", "032_stock",
                 "035_targets", "040_lead_small_gaps", "041_settings_amend_reopen",
                 "042_dealer_tasks", "048_complaint_escalation")

_NAME = re.compile(r"CREATE POLICY (\w+)")


def _load(name: str) -> ModuleType | None:
    path = _VERSIONS / f"{name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"mig_grants_{name}", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _modules() -> list[ModuleType]:
    return [m for name in _MODULE_NAMES if (m := _load(name)) is not None]


def _table_verbs(verbs: str) -> set[str]:
    """The table-wide verbs in a GRANT list. A verb with a column list (013's
    `UPDATE (party_name, ...)` on sales_order) is not a table privilege:
    has_table_privilege() answers false for it, and the column grants are
    asserted by the migration's own tests."""
    out: set[str] = set()
    depth, item = 0, ""
    for ch in verbs + ",":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            if "(" not in item:
                out.add(item.strip())
            item = ""
        else:
            item += ch
    return out


def grants() -> dict[str, set[str]]:
    """table -> the set of verbs app_role holds, unioned across migrations."""
    out: dict[str, set[str]] = {}
    for mod in _modules():
        for table, verbs in getattr(mod, "GRANTS", {}).items():
            out.setdefault(table, set()).update(_table_verbs(verbs))
    return out


def hand_policies() -> list[tuple[str, str]]:
    """(table, CREATE POLICY statement), last-declaration-wins by (table, name)."""
    latest: dict[tuple[str, str], str] = {}
    order: list[tuple[str, str]] = []
    for mod in _modules():
        for table, stmt in getattr(mod, "HAND_POLICIES", []):
            match = _NAME.search(stmt)
            key = (table, match.group(1)) if match else (table, stmt)
            if key not in latest:
                order.append(key)
            latest[key] = stmt
    return [(table, latest[key]) for key in order for (table, _) in [key]]
