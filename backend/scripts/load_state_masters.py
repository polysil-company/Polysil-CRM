"""Load the CG, RJ and UP subsidy schemes from the state fixtures (FS-056).

Reads `tests/fixtures/subsidy/states.json` (the scheme tables) and
`states_samples.json` (the company's rates and quantities), which
`scripts/extract_state_masters.py` writes from the client's workbooks. Runs as the
table owner, as the GGRC loader does.

Per state:
- the scheme: the one linked to the state's territory (code CG, RJ, UP), else the
  one with that code, else a new scheme with the state's stages copied from GGRC;
- per system: the `subsidy_system` row (pipeline, table shape, cap mode, rounding),
  then categories, parameters, the unit cost table, quantities and component
  rates, each effective from `--effective-from`.

**Idempotent per system.** A system already loaded from that date is skipped
whole. A later `--effective-from` is a revision: the rows in force end on that
date (half-open) and the new ones start. An earlier date is refused.

    python scripts/load_state_masters.py                    # all three states
    python scripts/load_state_masters.py --state UP --dry-run
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "subsidy"
DEFAULT_EFFECTIVE_FROM = dt.date(2026, 9, 15)       # the CG and RJ formats' arrival
STATES = {"CG": "Chhattisgarh micro irrigation", "RJ": "Rajasthan micro irrigation",
          "UP": "Uttar Pradesh micro irrigation"}
FLAGS = {"min_area_prorate", "max_area_scaling", "jantri_guards", "share_floor_zero",
         "pipe_size_from_input", "unit_cost_round_rupee", "zero_above_max_area",
         "exact_area_match_required"}
RUPEES = {"flat_inspection", "head_unit_deduction", "inspection_floor", "education_amount"}
HECTARES = {"seven_year_area_min", "seven_year_area_max", "pipe_size_band_ha", "gsdma_max_area"}
TABLES = ("subsidy_category", "subsidy_parameter", "unit_cost_matrix", "quantity_matrix",
          "subsidy_component_rate")


def _unit(key: str) -> str:
    if key in FLAGS:
        return "flag"
    if key in RUPEES:
        return "rupees"
    if key in HECTARES:
        return "hectares"
    return "ratio"


class Loader:
    def __init__(self, conn: Any, *, effective_from: dt.date) -> None:
        self.conn = conn
        self.on = effective_from
        self.written: list[str] = []
        self.skipped: list[str] = []

    def one(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        row = self.conn.execute(sql, params or {}).fetchone()
        return None if row is None else row[0]

    def x(self, sql: str, params: dict[str, Any] | None = None) -> None:
        self.conn.execute(sql, params or {})

    def scheme(self, code: str) -> str:
        state = self.one("SELECT id FROM territory WHERE level = 'state' AND code = %(c)s "
                         "AND deleted_at IS NULL", {"c": code})
        sid = None
        if state is not None:
            sid = self.one("SELECT id FROM subsidy_scheme WHERE state_territory_id = %(t)s "
                           "AND is_active", {"t": state})
        if sid is None:
            sid = self.one("SELECT id FROM subsidy_scheme WHERE code = %(c)s", {"c": code})
        if sid is not None:
            return str(sid)
        sid = self.one("INSERT INTO subsidy_scheme (code, name, state_territory_id, is_active) "
                       "VALUES (%(c)s, %(n)s, %(t)s, true) RETURNING id",
                       {"c": code, "n": STATES[code], "t": state})
        # the application stages, as subsidy_scheme_create copies them (FS-039)
        ggrc = self.one("SELECT id FROM subsidy_scheme WHERE code = 'GGRC'")
        self.x("INSERT INTO subsidy_stage_def (scheme_id, seq, code, name, is_active) "
               "SELECT %(n)s, seq, code, name, is_active FROM subsidy_stage_def WHERE scheme_id = %(g)s",
               {"n": sid, "g": ggrc})
        self.x("INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, "
               "is_required, pairs_with_key, sort_order, is_active) "
               "SELECT %(n)s, nd.id, f.field_key, f.label, f.type, f.is_required, f.pairs_with_key, "
               "f.sort_order, f.is_active FROM subsidy_stage_field f "
               "JOIN subsidy_stage_def od ON od.id = f.stage_def_id "
               "JOIN subsidy_stage_def nd ON nd.scheme_id = %(n)s AND nd.code = od.code "
               "WHERE f.scheme_id = %(g)s", {"n": sid, "g": ggrc})
        self.written.append(f"scheme {code} (linked to state {code}: {state is not None})")
        return str(sid)

    def system(self, sid: str, key: str, pub: dict[str, Any], smp: dict[str, Any]) -> None:
        st = pub["system_type"]
        p = {"s": sid, "t": st, "d": self.on}
        # a re-run on the same date writes nothing; a later date is a revision that
        # ends what is in force (code review F-1); an earlier one would overlap
        latest = self.one(
            "SELECT max(effective_from) FROM unit_cost_matrix WHERE scheme_id = %(s)s "
            "AND system_type = %(t)s::subsidy_system_type AND variant = 'regular'", p)
        if latest is not None and latest == self.on:
            self.skipped.append(f"{key}: already loaded from {self.on}")
            return
        if latest is not None and latest > self.on:
            raise SystemExit(f"{key}: a table from {latest} exists; load from a later date")
        y = pub["system"]
        version = f"{key.split('/')[0].lower()}-{self.on.isoformat()}"
        self.x("""INSERT INTO subsidy_system (scheme_id, system_type, pipeline_variant, jantri_variant,
                  quantity_source, has_head_unit, supports_group, crop_count_max, rounded_blocks,
                  rounded_lines, spacing_rule, spacing_outside_table, formula_version, cap_mode, is_active)
                  VALUES (%(s)s, %(t)s::subsidy_system_type, %(pl)s::subsidy_pipeline_variant,
                  %(jv)s::subsidy_jantri_variant, %(qs)s::subsidy_quantity_source, %(hh)s, %(sg)s,
                  %(cc)s, %(rb)s, %(rl)s, %(sr)s::subsidy_spacing_rule, %(so)s::subsidy_outside_table,
                  %(fv)s, %(cm)s, true)
                  ON CONFLICT (scheme_id, system_type) DO UPDATE SET
                  pipeline_variant = EXCLUDED.pipeline_variant, jantri_variant = EXCLUDED.jantri_variant,
                  quantity_source = EXCLUDED.quantity_source, has_head_unit = EXCLUDED.has_head_unit,
                  supports_group = EXCLUDED.supports_group, crop_count_max = EXCLUDED.crop_count_max,
                  rounded_blocks = EXCLUDED.rounded_blocks, rounded_lines = EXCLUDED.rounded_lines,
                  spacing_rule = EXCLUDED.spacing_rule, spacing_outside_table = EXCLUDED.spacing_outside_table,
                  formula_version = EXCLUDED.formula_version, cap_mode = EXCLUDED.cap_mode, is_active = true""",
               {**p, "pl": y["pipeline"], "jv": y["jantri_variant"], "qs": y["quantity_source"],
                "hh": y["has_head_unit"], "sg": y["supports_group"], "cc": y["crop_count_max"],
                "rb": y["rounded_blocks"], "rl": y["rounded_lines"], "sr": y["spacing_rule"],
                "so": y["spacing_outside_table"], "fv": version, "cm": y["cap_mode"]})
        # a revision: whatever is in force ends the day the new rows start
        for table in TABLES:
            self.x(f"UPDATE {table} SET effective_to = %(d)s WHERE scheme_id = %(s)s "
                   f"AND system_type = %(t)s::subsidy_system_type AND effective_to IS NULL "
                   f"AND effective_from < %(d)s", p)
        for c in pub["categories"]:
            self.x("INSERT INTO subsidy_category (scheme_id, system_type, code, name, pct, variant, "
                   "sort_order, effective_from) VALUES (%(s)s, %(t)s::subsidy_system_type, %(c)s, %(n)s, "
                   "%(pct)s, %(v)s::subsidy_matrix_variant, %(o)s, %(d)s)",
                   {**p, "c": c["code"], "n": c["name"], "pct": Decimal(c["pct"]), "v": c["variant"],
                    "o": c["sort_order"]})
        for k, v in pub["parameters"].items():
            self.x("INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, effective_from) "
                   "VALUES (%(s)s, %(t)s::subsidy_system_type, %(k)s, %(v)s, %(u)s::subsidy_param_unit, %(d)s)",
                   {**p, "k": k, "v": Decimal(v), "u": _unit(k)})
        self._unit_cost(p, key, pub["unit_cost"], y["jantri_variant"])
        if smp.get("quantities"):
            q = smp["quantities"]
            qid = self.one("INSERT INTO quantity_matrix (scheme_id, system_type, effective_from, source) "
                           "VALUES (%(s)s, %(t)s::subsidy_system_type, %(d)s, %(src)s) RETURNING id",
                           {**p, "src": f"{key} quantity table"})
            for code, row in q["rows"].items():
                for area, qty in row.items():
                    self.x("INSERT INTO quantity_matrix_cell (matrix_id, component_code, area_breakpoint, qty) "
                           "VALUES (%(m)s, %(c)s, %(a)s, %(q)s)",
                           {"m": qid, "c": code, "a": Decimal(area), "q": Decimal(qty)})
        for r in smp.get("component_rates", []):
            self.x("INSERT INTO subsidy_component_rate (scheme_id, system_type, component_code, description, "
                   "uom, pipe_size_mm, nozzle, rate, source_cell, effective_from) VALUES (%(s)s, "
                   "%(t)s::subsidy_system_type, %(c)s, %(de)s, %(u)s, %(ps)s, %(nz)s::subsidy_nozzle, %(r)s, "
                   "%(src)s, %(d)s)",
                   {**p, "c": r["code"], "de": r["description"], "u": r["uom"], "ps": r["pipe_size_mm"],
                    "nz": r["nozzle"], "r": Decimal(r["rate"]), "src": f"{key} price list"})
        self.written.append(f"{key}: {y['pipeline']} / {y['jantri_variant']} / {y['cap_mode']}")

    def _unit_cost(self, p: dict[str, Any], key: str, uc: dict[str, Any], variant: str) -> None:
        dim = 2 if variant in ("bilinear_2d", "size_area_2d", "label_anchor_linear") else 1
        mid = self.one("INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, "
                       "effective_from, source) VALUES (%(s)s, %(t)s::subsidy_system_type, 'regular', "
                       "%(dim)s, %(d)s, %(src)s) RETURNING id",
                       {**p, "dim": dim, "src": f"{key} unit cost table"})
        cells: list[tuple[Decimal | None, str | None, Decimal, Decimal]] = []
        if uc["kind"] == "bilinear_2d":
            areas = [Decimal(a) for a in uc["areas"]]
            for r in uc["rows"]:
                cells += [(Decimal(r["spacing"]), None, a, Decimal(c))
                          for a, c in zip(areas, r["costs"], strict=True)]
        else:
            for name, row in uc["rows"].items():
                if variant == "size_area_2d":
                    cells += [(Decimal(name), None, Decimal(a), Decimal(v)) for a, v in row.items()]
                else:
                    label = " ".join(str(name).split())
                    cells += [(None, label, Decimal(a), Decimal(v)) for a, v in row.items()]
        for spacing, label, area, cost in cells:
            self.x("INSERT INTO unit_cost_cell (matrix_id, lateral_spacing, row_label, area_breakpoint, "
                   "unit_cost) VALUES (%(m)s, %(sp)s, %(l)s, %(a)s, %(c)s)",
                   {"m": mid, "sp": spacing, "l": label, "a": area, "c": cost})


def load(conn: Any, *, effective_from: dt.date, states: tuple[str, ...] = tuple(STATES)) -> Loader:
    pub = json.loads((FIXTURES / "states.json").read_text(encoding="utf-8"))
    smp = json.loads((FIXTURES / "states_samples.json").read_text(encoding="utf-8"))
    loader = Loader(conn, effective_from=effective_from)
    for state in states:
        sid = loader.scheme(state)
        for key in (k for k in pub if k.startswith(f"{state}/")):
            loader.system(sid, key, pub[key], smp.get(key, {}))
    return loader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--effective-from", type=dt.date.fromisoformat, default=DEFAULT_EFFECTIVE_FROM)
    parser.add_argument("--state", choices=tuple(STATES), action="append")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)

    import psycopg

    from api.config import get_settings

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn) as conn:
        loader = load(conn, effective_from=args.effective_from,
                      states=tuple(args.state or STATES))
        conn.rollback() if args.dry_run else conn.commit()
    for line in loader.written:
        print("  wrote  ", line)
    for line in loader.skipped:
        print("  skipped", line)
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
