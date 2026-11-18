"""FS-069 rule 11: an order from several quotations takes their freight summed, and
a slab only when every quotation with freight chose the same one."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from api.domain.pricing.tax import CHARGE_KINDS
from api.services.orders import _quotations_charges, _quotations_freight

D = Decimal


def q(amount: str | None, slab: str = "18", chosen: bool = False) -> SimpleNamespace:
    return SimpleNamespace(freight_amount=None if amount is None else D(amount),
                           freight_slab=D(slab), freight_slab_chosen=chosen)


def test_no_quotation_with_freight_gives_none() -> None:
    assert _quotations_freight([q(None), q(None)]) is None


def test_the_amounts_add_and_one_shared_choice_is_kept() -> None:
    f = _quotations_freight([q("100.00", "5", True), q(None), q("50.50", "5", True)])
    assert f is not None and (f.amount, f.gst_slab) == (D("150.50"), D(5))


def test_a_default_or_a_different_choice_falls_back_to_the_default() -> None:
    mixed = _quotations_freight([q("100", "5", True), q("100", "18", True)])
    with_default = _quotations_freight([q("100", "5", True), q("100", "5", False)])
    assert mixed is not None and mixed.gst_slab is None
    assert with_default is not None and with_default.gst_slab is None


# ── FS-088: each charge summed on its own ──────────────────────────────────

def _q(**cols: object) -> SimpleNamespace:
    base: dict[str, object] = {}
    for kind in CHARGE_KINDS:
        base.update({f"{kind}_amount": None, f"{kind}_slab": D(18), f"{kind}_slab_chosen": False})
    base.update(cols)
    return SimpleNamespace(**base)


def test_an_order_from_quotations_sums_each_charge_on_its_own() -> None:
    """Rule 8: one quotation with installation, another with freight and installation."""
    rows = [_q(installation_amount=D("100.00")),
            _q(freight_amount=D("50.00"), installation_amount=D("200.00"),
               installation_slab=D(5), installation_slab_chosen=True)]
    charges = _quotations_charges(rows)
    assert charges["installation"] is not None and charges["installation"].amount == D("300.00")
    assert charges["installation"].gst_slab is None, "one default and one choice: the default"
    assert charges["freight"] is not None and charges["freight"].amount == D("50.00")
    assert charges["fittings"] is None
    assert _quotations_freight(rows) == charges["freight"], "freight's own path is unchanged"
