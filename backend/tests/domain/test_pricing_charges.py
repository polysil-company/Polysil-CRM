"""FS-088: installation and fittings charges, taxed as freight is."""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.domain.pricing.tax import (
    CHARGE_DEFAULT_SLAB,
    CHARGE_KINDS,
    PricingError,
    compute_charge,
    compute_line,
    default_charge_slab,
    document_totals,
)
from api.domain.quotations import charge_rows, goods_subtotal

D = Decimal


def charge(kind: str, amount: str, slab: str, intra: bool = True):  # type: ignore[no-untyped-def]
    return compute_charge(kind, amount=D(amount), slab=D(slab), chosen=False, intra_state=intra)


def test_installation_defaults_to_18_and_the_others_to_the_highest_goods_slab() -> None:
    """Rule 3, GAP-591."""
    assert default_charge_slab("installation", [D(5), D(12)]) == D(18)
    assert default_charge_slab("fittings", [D(5), D(12)]) == D(12)
    assert default_charge_slab("freight", [D(5), D(12)]) == D(12)
    assert set(CHARGE_DEFAULT_SLAB) == {"installation"}


@pytest.mark.parametrize("kind", ["installation", "fittings"])
def test_a_charge_needs_a_goods_line(kind: str) -> None:
    with pytest.raises(PricingError) as exc:
        default_charge_slab(kind, [])
    assert (exc.value.code, exc.value.field_path) == ("charge_without_lines", kind)


def test_freight_keeps_its_own_codes() -> None:
    with pytest.raises(PricingError) as exc:
        default_charge_slab("freight", [])
    assert exc.value.code == "freight_without_lines"
    with pytest.raises(PricingError) as exc:
        charge("freight", "0.00", "18")
    assert exc.value.code == "freight_amount_invalid"


@pytest.mark.parametrize("amount", ["0.00", "-1.00", "1.005", "100000000.00"])
def test_a_bad_amount_names_the_charge(amount: str) -> None:
    with pytest.raises(PricingError) as exc:
        charge("fittings", amount, "18")
    assert (exc.value.code, exc.value.field_path) == ("charge_amount_invalid", "fittings.amount")


def test_a_slab_off_the_list_names_the_charge() -> None:
    with pytest.raises(PricingError) as exc:
        charge("installation", "100.00", "7")
    assert exc.value.field_path == "installation.gst_slab"


def test_each_charge_is_taxed_as_a_line_of_one() -> None:
    c = charge("installation", "1000.00", "18")
    assert (c.kind, c.money.cgst, c.money.sgst, c.money.igst, c.money.total) == (
        "installation", D("90.00"), D("90.00"), D("0.00"), D("1180.00"))
    inter = charge("installation", "1000.00", "18", intra=False)
    assert (inter.money.cgst, inter.money.igst) == (D("0.00"), D("180.00"))


def test_every_charge_joins_taxable_tax_and_total_but_never_gross_or_discount() -> None:
    """Rule 6."""
    goods = compute_line(rate=D("100.00"), qty=D("10"), discounts=(D(10),), slab=D(5),
                         intra_state=True)
    f, i, t = (charge("freight", "50.00", "5"), charge("installation", "1000.00", "18"),
               charge("fittings", "200.00", "5"))
    totals = document_totals((goods,), f, i, t)
    assert (totals.gross, totals.discount) == (goods.gross, goods.discount)
    assert totals.taxable == goods.taxable + D("1250.00")
    assert totals.taxable == totals.gross - totals.discount + D("1250.00"), "the 089 identity"
    assert totals.total == goods.total + f.money.total + i.money.total + t.money.total
    assert totals.cgst == goods.cgst + f.money.cgst + i.money.cgst + t.money.cgst


def test_three_charges_round_each_on_its_own() -> None:
    """EC-8: three 1.05 charges at 18 % intra-state are 0.09 CGST each, 0.27 in all; one
    combined 3.15 would be 0.28. The sum of rounded rows is the rule."""
    goods = compute_line(rate=D("1.00"), qty=D("1"), slab=D(18), intra_state=True)
    rows = [charge(k, "1.05", "18") for k in CHARGE_KINDS]
    assert [r.money.cgst for r in rows] == [D("0.09")] * 3
    assert document_totals((goods,), *rows).cgst == goods.cgst + D("0.27")


def test_document_totals_still_takes_no_charge_or_a_none() -> None:
    goods = compute_line(rate=D("100.00"), qty=D("1"), slab=D(5), intra_state=True)
    assert document_totals((goods,)) == document_totals((goods,), None, None)


def _doc(**charges: str) -> dict[str, object]:
    doc: dict[str, object] = {"taxable": "3288.10", "intra_state": True}
    for kind in CHARGE_KINDS:
        doc[f"{kind}_amount"] = None
    for kind, amount in charges.items():
        tax = D(amount) * D("0.09")
        doc.update({f"{kind}_amount": amount, f"{kind}_slab": "18", f"{kind}_cgst": f"{tax:.2f}",
                    f"{kind}_sgst": f"{tax:.2f}", f"{kind}_igst": "0.00",
                    f"{kind}_total": f"{D(amount) + 2 * tax:.2f}"})
    return doc


def test_the_pdf_rows_come_in_print_order_with_their_labels() -> None:
    """Rule 11: Transportation, Installation Charges, Fittings Material Charges."""
    rows = charge_rows(_doc(fittings="200.00", freight="500.00", installation="1000.00"))
    assert [r["label"] for r in rows] == ["Transportation", "Installation Charges",
                                          "Fittings Material Charges"]
    assert rows[1]["cgst_rate"] == D(9) and rows[1]["igst_rate"] == D(0)
    assert charge_rows(_doc()) == []


def test_the_goods_sub_total_takes_out_every_charge() -> None:
    """Rule 14."""
    assert goods_subtotal(_doc(freight="500.00", installation="1000.00", fittings="200.00")) \
        == D("1588.10")
    assert goods_subtotal(_doc(installation="1000.00")) == D("2288.10")
