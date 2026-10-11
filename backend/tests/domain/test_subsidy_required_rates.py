# ruff: noqa: E501

"""FS-039: `required_rates` names every rate `field_inspection` looks up, so the
readiness panel cannot call a sprinkler scheme ready that a calculation refuses.
No samples needed: the masters are made up, and every lookup is recorded."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal

import pytest

from api.domain.subsidy.defaults import SPRINKLER_COMPONENT_ORDER
from api.domain.subsidy.money import RoundingPolicy
from api.domain.subsidy.sprinkler import (
    NOZZLES,
    field_inspection,
    missing_quantity_rows,
    required_rates,
)
from api.domain.subsidy.types import (
    Category,
    ComponentRate,
    CropInput,
    Masters,
    QuantityMatrix,
    QuotationInput,
    SubsidyError,
    SystemPolicy,
    rate_matches,
)

D = Decimal
AREAS = (D("0.4"), D("1.0"), D("2.0"), D("2.01"), D("3.0"))


@dataclass(frozen=True)
class Recording(Masters):
    """Answers every rate lookup with 1 and writes down what was asked."""

    asked: list[tuple[str, int | None, str | None]] = field(default_factory=list)

    def rate_for(self, code: str, *, pipe_size_mm: int | None = None,
                 nozzle: str | None = None) -> ComponentRate:
        self.asked.append((code, pipe_size_mm, nozzle))
        return ComponentRate(code, code, "No", D(1), pipe_size_mm, nozzle)


def _masters(areas: tuple[Decimal, ...] = AREAS) -> Recording:
    rows = {code: dict.fromkeys(areas, D(1)) for code in SPRINKLER_COMPONENT_ORDER if code != "nozzle"}
    rows |= {f"nozzle_{n}": dict.fromkeys(areas, D(1)) for n in NOZZLES}
    table = dict.fromkeys(areas, D(100000))
    return Recording(table, table, (Category("general", "General", D(50), "regular"),),
                     {}, QuantityMatrix(areas, rows), ())


@pytest.mark.parametrize("band", [D("2.0"), D("1.0"), D("5.0")])
def test_required_rates_is_exactly_what_field_inspection_asks_for(band: Decimal) -> None:
    m = _masters()
    for area in AREAS:
        for nozzle in NOZZLES:
            q = QuotationInput("sprinkler", (CropInput("Wheat", None, area, "", D(0)),), nozzle=nozzle)
            field_inspection(q, m, SystemPolicy("sprinkler", RoundingPolicy(frozenset(), frozenset()),
                                                pipe_size_band_ha=band))
    assert set(required_rates(AREAS, band)) == set(m.asked)


def test_a_rate_missing_from_the_list_is_one_a_calculation_refuses() -> None:
    """The other direction: rates for everything listed but one, through the real
    `rate_for`, and the calculation that needs the missing one refuses."""
    need = required_rates(AREAS, D("2.0"))
    dropped = ("lateral", 90, None) if ("lateral", 90, None) in need else need[0]
    rates = tuple(ComponentRate(c, c, "No", D(1), s, n) for c, s, n in need if (c, s, n) != dropped)
    base = _masters()
    real = Masters(base.regular, base.seven_year, base.categories, {}, base.quantities, rates)
    assert not any(rate_matches(r, *dropped) for r in rates)
    with pytest.raises(SubsidyError) as err:
        for area in AREAS:
            for nozzle in NOZZLES:
                q = QuotationInput("sprinkler", (CropInput("Wheat", None, area, "", D(0)),), nozzle=nozzle)
                field_inspection(q, real, SystemPolicy("sprinkler", RoundingPolicy(frozenset(), frozenset())))
    assert err.value.code == "component_rate_missing"


def test_only_the_sizes_the_areas_reach_are_required() -> None:
    small = required_rates((D("0.4"), D("1.0")), D("2.0"))
    assert {s for _c, s, _n in small if s is not None} == {75}
    assert ("nozzle", None, "plastic") in small and ("transport", None, None) in small


def test_missing_quantity_rows_names_absent_and_short_rows() -> None:
    """Code review F-1: each named row would be a KeyError in `field_inspection`."""
    full = _masters().quantities
    assert full is not None and missing_quantity_rows(full) == ()
    rows = {k: dict(v) for k, v in full.rows.items()}
    del rows["riser"]
    del rows["nozzle_brass"][AREAS[-1]]
    rows["transport"] = {AREAS[0]: D(1)}            # optional, but read when present
    short = QuantityMatrix(full.areas, rows)
    assert missing_quantity_rows(short) == ("riser", "nozzle_brass", "transport")
    with pytest.raises(KeyError):
        for area in AREAS:
            q = QuotationInput("sprinkler", (CropInput("Wheat", None, area, "", D(0)),), nozzle="brass")
            field_inspection(q, replace(_masters(), quantities=short),
                             SystemPolicy("sprinkler", RoundingPolicy(frozenset(), frozenset())))
