"""Masters and inputs built from the committed workbook fixtures, so the domain
tests run on a box without `data/`. Not a test module: the golden and boundary
tests import it.
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal
from typing import Any

import pytest

from api.domain.subsidy.defaults import CATEGORIES, POLICIES, SPRINKLER_RATES
from api.domain.subsidy.jantri import Matrix2D, table_1d
from api.domain.subsidy.types import (
    CropInput,
    Line,
    Masters,
    QuantityMatrix,
    QuotationInput,
    SystemPolicy,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "subsidy"
MATRICES: dict[str, Any] = json.loads((FIXTURES / "matrices.json").read_text(encoding="utf-8"))
D = Decimal

SAMPLES = ("drip", "mini_sprinkler", "sprinkler")
# The three sample quotations carry the client's own component rates, so they are
# kept out of the shared snapshot while `matrices.json` (the scheme's published
# tables) travels with it. Everything that needs a sample skips when it is absent;
# the interpolation, the brackets and the clamps still run on the matrices alone.
SAMPLES_PRESENT = all((FIXTURES / f"{s}.json").exists() for s in SAMPLES)
NO_SAMPLES = "the sample quotation fixtures are not in this checkout"

needs_samples = pytest.mark.skipif(not SAMPLES_PRESENT, reason=NO_SAMPLES)


def fixture(system: str) -> dict[str, Any]:
    path = FIXTURES / f"{system}.json"
    if not path.exists():
        pytest.skip(NO_SAMPLES)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def cell(fix: dict[str, Any], key: str) -> dict[str, Any]:
    node: dict[str, Any] = fix["expected"][key]
    return node


def value(fix: dict[str, Any], key: str) -> Decimal:
    return D(str(cell(fix, key)["value"]))


def matrix_2d(system: str, variant: str) -> Matrix2D:
    m = MATRICES[system][variant]
    return Matrix2D.from_rows(m["areas"], [(r["spacing"], r["costs"]) for r in m["rows"]])


def crop_spacings() -> dict[str, Decimal]:
    return {" ".join(str(r["crop"]).split()).lower(): D(str(r["standard_spacing"]))
            for r in MATRICES["crops"]["rows"]}


def quantity_matrix() -> QuantityMatrix:
    q = MATRICES["sprinkler"]["quantities"]
    areas = tuple(D(str(a)) for a in q["areas"])
    rows = {c["code"]: dict(zip(areas, (D(str(v)) for v in c["qty"]), strict=True))
            for c in q["components"]}
    return QuantityMatrix(areas, rows)


def masters(system: str) -> Masters:
    if system == "sprinkler":
        return Masters(
            regular=table_1d((r["area"], r["cost"])
                             for r in MATRICES["sprinkler"]["regular"]["rows"]),
            seven_year=table_1d((r["area"], r["cost"])
                                for r in MATRICES["sprinkler"]["seven_year"]["rows"]),
            categories=CATEGORIES[system],
            standard_spacings=crop_spacings(),
            quantities=quantity_matrix(),
            component_rates=SPRINKLER_RATES,
            formula_version="ggrc-workbooks",
        )
    return Masters(regular=matrix_2d(system, "regular"), seven_year=matrix_2d(system, "seven_year"),
                   categories=CATEGORIES[system], standard_spacings=crop_spacings(),
                   formula_version="ggrc-workbooks")


def policy(system: str) -> SystemPolicy:
    return POLICIES[system]


def _lines(rows: list[dict[str, Any]]) -> tuple[Line, ...]:
    return tuple(Line(r["description"], r["uom"], D(str(r["rate"])), D(str(r["qty"])))
                 for r in rows)


def quotation(system: str) -> QuotationInput:
    """The sample quotation the workbook itself computes."""
    inp = fixture(system)["inputs"]
    crops = tuple(CropInput(c["crop"], c["inter_crop"], D(str(c["area"])), c["crop_spacing"],
                            D(str(c["lateral_spacing"])), _lines(c.get("lines", [])))
                  for c in inp["crops"])
    if system == "sprinkler":
        return QuotationInput(system, crops, nozzle=inp["nozzle"])
    group = inp.get("group_total_area")
    return QuotationInput(
        system, crops, head_lines=_lines(inp["head_lines"]),
        sump_rate_per_ha=D(str(inp["sump"]["rate_per_ha"])),
        group_total_area=D(str(group)) if group is not None else None,
        installation_rate_per_ha=D(str(inp["installation_rate_per_ha"])),
    )
