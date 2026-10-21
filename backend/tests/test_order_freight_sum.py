"""FS-069 rule 11: an order from several quotations takes their freight summed, and
a slab only when every quotation with freight chose the same one."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from api.services.orders import _quotations_freight

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
