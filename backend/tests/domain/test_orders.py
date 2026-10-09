"""FS-011's rules that need no database (api/domain/orders.py), and the two
lists that must agree with migration 013: the order types and the SQLSTATEs."""

from __future__ import annotations

import itertools
import re
from decimal import Decimal
from pathlib import Path

import pytest

from api.domain import orders as domain

_VERSIONS = Path(__file__).resolve().parents[2] / "api/db/migrations/versions"
MIGRATION = (_VERSIONS / "013_orders_approvals_dispatch.py").read_text("utf-8")
# the engine's later arms raise through the same map (FS-013)
ENGINE = MIGRATION + (_VERSIONS / "017_quotation_discount_approval.py").read_text("utf-8")


def test_every_custom_sqlstate_the_migration_raises_has_an_api_error_and_no_other() -> None:
    """A code missing from the map reaches the frontend as a 500; a stale entry
    documents an error that cannot happen."""
    raised = {c for c in re.findall(r"ERRCODE = '([A-Z0-9]{5})'", ENGINE)
              if not c[0].isdigit()}
    # FS-022 and FS-023 reach the order paths too: dispatch_record resolves a
    # warehouse (032) and a paid order's dealer is fixed (031)
    later = ((_VERSIONS / "031_payments.py").read_text("utf-8")
             + (_VERSIONS / "032_stock.py").read_text("utf-8"))
    # FS-036: order_amend (041)
    later += (_VERSIONS / "041_settings_amend_reopen.py").read_text("utf-8")
    # FS-027: order_submit's credit check (047)
    later += (_VERSIONS / "047_dealer_credit_limit.py").read_text("utf-8")
    # FS-042: order_submit's export and sample gates (045)
    later += (_VERSIONS / "045_export_sample_orders.py").read_text("utf-8")
    through_orders = {"STKWI", "STKNW", "STKNF", "PAYPC", "ORDTF", "ORDPA", "CRDLM",
                      "ORDXS", "ORDSF", "ORDSL", "ORDLT", "ORDLX"}
    assert through_orders <= set(re.findall(r"ERRCODE = '([A-Z0-9]{5})'", later))
    expected = raised | through_orders
    assert expected == set(domain.SQLSTATE_TO_ERROR), expected ^ set(domain.SQLSTATE_TO_ERROR)


def test_every_order_type_is_either_priced_or_names_its_question() -> None:
    enum = re.search(r"CREATE TYPE order_type AS ENUM \(([^)]*)\)", MIGRATION)
    assert enum is not None
    types = set(re.findall(r"'([a-z_]+)'", enum.group(1)))
    assert domain.TYPES_ACCEPTED | set(domain.TYPE_BLOCKED_ON) == types
    assert not domain.TYPES_ACCEPTED & set(domain.TYPE_BLOCKED_ON)


@pytest.mark.parametrize(("lines", "problems"), [
    ([], {"lines": "At least one line."}),
    (["a"], {}),
    (["a", "b"], {}),
    (["a", "b", "a"], {"lines[2].order_line_id": "This line is already in the dispatch."}),
    (["a", "a", "a"], {"lines[1].order_line_id": "This line is already in the dispatch.",
                       "lines[2].order_line_id": "This line is already in the dispatch."}),
])
def test_dispatch_line_problems(lines: list[str], problems: dict[str, str]) -> None:
    assert domain.dispatch_line_problems(lines) == problems


@pytest.mark.parametrize(("ordered", "sent", "pct"), [
    ("0", "0", 0),
    ("0", "5", 0),
    ("10", "0", 0),
    ("3", "2.999", 99),          # rounded down: 100 only when everything went
    ("3", "3", 100),
    ("10", "12", 100),           # never above 100
    ("10", "-1", 0),             # never below 0
    ("1000.500", "500.250", 50),
])
def test_dispatched_pct(ordered: str, sent: str, pct: int) -> None:
    assert domain.dispatched_pct(Decimal(ordered), Decimal(sent)) == pct


def test_open_quantity_is_what_is_left_and_never_negative() -> None:
    """The exhaustive small grid stands in for a property test: every mix of sent
    and short within and past the ordered quantity, at three places."""
    steps = [Decimal(n) / 1000 for n in (0, 1, 999, 1000, 4500, 9999, 10000, 10001)]
    qty = Decimal("10")
    for sent, short in itertools.product(steps, repeat=2):
        left = domain.open_quantity(qty, sent, short)
        assert left >= 0
        assert left == max(Decimal(0), qty - sent - short)
        if sent + short <= qty:
            assert left + sent + short == qty


def test_the_orderable_lead_stages_are_qualified_or_later_and_open() -> None:
    assert {"qualified", "quoted", "negotiation", "won"} == domain.LEAD_STAGES_ORDERABLE


# ── FS-042: export and sample ────────────────────────────────────────────────

@pytest.mark.parametrize(("order_type", "setting", "treatment"), [
    ("export", "lut", "export_lut"),
    ("export", "igst", "export_igst"),
    ("commercial", "lut", "domestic"),
    ("sample", "igst", "domestic"),
])
def test_the_treatment_comes_from_the_setting_for_an_export_only(
        order_type: str, setting: str, treatment: str) -> None:
    assert domain.treatment_for(order_type, setting) == treatment


@pytest.mark.parametrize(("order_type", "country", "gstin", "codes"), [
    ("export", "Kenya", None, {}),
    ("export", None, None, {"export_country": "export_country_required"}),
    ("export", " K ", None, {"export_country": "export_country_required"}),
    ("export", "Kenya", "24AAACP1234A1Z5", {"party.gstin": "export_party_gstin"}),
    ("commercial", None, "24AAACP1234A1Z5", {}),
    ("commercial", "Kenya", None, {"export_country": "export_country_not_export"}),
])
def test_export_problems(order_type: str, country: str | None, gstin: str | None,
                         codes: dict[str, str]) -> None:
    got = domain.export_problems(order_type, country, gstin)
    assert {k: c for k, (c, _) in got.items()} == codes


def test_a_free_sample_is_every_line_at_full_discount_on_tier_one() -> None:
    assert (Decimal(100), Decimal(0), Decimal(0)) == domain.FREE_DISCOUNTS
    assert {"export", "sample"} == domain.STAFF_ONLY_TYPES
