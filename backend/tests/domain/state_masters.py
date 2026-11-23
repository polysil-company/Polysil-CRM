"""FS-056: engine inputs built from the state fixtures (`states.json`, the scheme
tables; `states_samples.json`, the company's rates and the worked examples).
Not a test module. `scripts/extract_state_masters.py` writes both from the
client's workbooks; the samples file stays out of the shared snapshot.
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal
from typing import Any

import pytest

from api.domain.subsidy import pipeline, sprinkler, state_pipelines
from api.domain.subsidy.jantri import Matrix2D, OutsideTable, RowTable
from api.domain.subsidy.money import RoundingPolicy
from api.domain.subsidy.types import (
    Category,
    ComponentRate,
    CropInput,
    Line,
    Masters,
    QuantityMatrix,
    QuotationInput,
    QuotationResult,
    SystemPolicy,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "subsidy"
PUBLIC: dict[str, Any] = json.loads((FIXTURES / "states.json").read_text(encoding="utf-8"))
SAMPLES_PATH = FIXTURES / "states_samples.json"
SAMPLES: dict[str, Any] = (json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
                           if SAMPLES_PATH.exists() else {})
needs_state_samples = pytest.mark.skipif(not SAMPLES, reason="the state sample fixtures are not "
                                                             "in this checkout")
ENTRIES = tuple(PUBLIC)
FLAGS = {"min_area_prorate", "max_area_scaling", "jantri_guards", "share_floor_zero",
         "pipe_size_from_input", "unit_cost_round_rupee", "zero_above_max_area",
         "exact_area_match_required", "subsidy_round_rupee", "transport_flat"}
D = Decimal


def policy(key: str) -> SystemPolicy:
    p = PUBLIC[key]
    system = p["system"]
    params = {k: (v == "1" if k in FLAGS else D(v)) for k, v in p["parameters"].items()}
    return SystemPolicy(
        system_type=p["system_type"],
        rounding=RoundingPolicy(frozenset(system["rounded_blocks"]),
                                frozenset(system["rounded_lines"])),
        spacing_rule=system["spacing_rule"],
        spacing_outside_table=OutsideTable(system["spacing_outside_table"]),
        cap_mode=system["cap_mode"],
        rates_include_gst=system["pipeline"] == "gst_inclusive" and p["system_type"] == "sprinkler",
        **params)


def unit_cost(key: str) -> Matrix2D | RowTable | dict[Decimal, Decimal]:
    uc = PUBLIC[key].get("unit_cost")
    if uc is None:
        return {}           # FS-063: AP drip has no table; the portal gives the guided cost
    if uc["kind"] == "bilinear_2d":
        return Matrix2D.from_rows(uc["areas"], [(r["spacing"], r["costs"]) for r in uc["rows"]])
    return RowTable({RowTable.key(k): {D(a): D(v) for a, v in row.items()}
                     for k, row in uc["rows"].items()})


def masters(key: str) -> Masters:
    p, s = PUBLIC[key], SAMPLES.get(key, {"component_rates": [], "quantities": None})
    cats = tuple(Category(c["code"], c["name"], D(c["pct"]), c["variant"],
                          sort_order=c["sort_order"]) for c in p["categories"])
    rates = tuple(ComponentRate(c["code"], c["description"], c["uom"], D(c["rate"]),
                                c["pipe_size_mm"], c["nozzle"]) for c in s["component_rates"])
    qm = None
    if s["quantities"]:
        qm = QuantityMatrix(tuple(D(a) for a in s["quantities"]["areas"]),
                            {k: {D(a): D(v) for a, v in row.items()}
                             for k, row in s["quantities"]["rows"].items()})
    return Masters(regular=unit_cost(key), seven_year=None, categories=cats, quantities=qm,
                   component_rates=rates)


def _lines(rows: list[dict[str, str]]) -> tuple[Line, ...]:
    return tuple(Line(r["description"], r["uom"], D(r["rate"]), D(r["qty"])) for r in rows)


def example(key: str) -> QuotationInput:
    inp = SAMPLES[key]["example"]["input"]
    crops = tuple(CropInput(c["crop"], None, D(c["area"]), "", D(c["lateral_spacing"] or "0"),
                            _lines(c["lines"])) for c in inp["crops"])
    return QuotationInput(
        PUBLIC[key]["system_type"], crops, _lines(inp["head_lines"]), D(inp["sump_rate_per_ha"]),
        D(inp["group_total_area"]) if inp["group_total_area"] else None,
        D(inp["installation_rate_per_ha"]), inp["nozzle"], inp["pipe_size_mm"],
        inp["spacing_label"], D(inp["hydrocyclone_m3"]), D(inp["gravel_filter_m3"]),
        inp["head_unit_existing"], inp["pvc_existing"],
        D(inp["guided_cost"]) if inp.get("guided_cost") else None,
        D(inp["fittings_amount"]) if inp.get("fittings_amount") else None)


def run(key: str, q: QuotationInput, m: Masters | None = None,
        pol: SystemPolicy | None = None) -> QuotationResult:
    """The service's dispatch (`api/services/subsidy.py` PIPELINES)."""
    p = PUBLIC[key]
    m, pol = m or masters(key), pol or policy(key)
    kind = p["system"]["pipeline"]
    if kind == "full_abcdefg":
        return pipeline.seven_block(q, m, pol)
    if kind == "field_inspection_only" or p["system_type"] == "sprinkler":
        return sprinkler.field_inspection(q, m, pol)
    if kind == "portal_manual":
        return state_pipelines.portal_manual(q, m, pol)
    if kind == "gst_inclusive":
        return state_pipelines.gst_inclusive_drip(q, m, pol)
    return state_pipelines.unit_cost_only(q, m, pol)
