"""The seeds: what the loader writes into the master tables and what the domain
tests run against. Every figure names the workbook cell it came from (FS-008
section 5, rules 10, 17, 20, 21). Categories are the workbooks' own rows in
their own order; the per-hectare caps are null on every row (rule 11, GAP-084).
"""

from __future__ import annotations

from decimal import Decimal

from api.domain.subsidy.money import (
    DRIP_ROUNDING,
    MINI_SPRINKLER_ROUNDING,
    SPRINKLER_ROUNDING,
)
from api.domain.subsidy.types import Category, ComponentRate, SystemPolicy

D = Decimal


def _cats(rows: list[tuple[str, str, str, str, str | None]]) -> tuple[Category, ...]:
    return tuple(Category(code, name, D(pct), variant, None, D(gsdma) if gsdma else None, i)
                 for i, (code, name, pct, variant, gsdma) in enumerate(rows))


# Drip 'Quo Summary'!N29:N36
DRIP_CATEGORIES = _cats([
    ("small_farmer", "Small Farmer 70 %", "70", "regular", None),
    ("darkzone_small_farmer", "Darkzone Small Farmer 80%", "80", "regular", None),
    ("big_farmer", "Big Farmer 70 %", "70", "regular", None),
    ("darkzone_big_farmer", "Darkzone Big Farmer 70 %", "70", "regular", None),
    ("sc_st", "SC+ST 85 %", "85", "regular", None),
    ("darkzone_sc_st", "Darkzone + SC/ST 90%", "90", "regular", None),
    ("seven_year_small", "7 Year Small farmer", "55", "seven_year", None),
    ("seven_year_big", "7 Year Big Farmer", "45", "seven_year", None),
])

# Mini 'Quo Summary'!L33:L40, with the GSDMA percent of Q43:Q48
MINI_SPRINKLER_CATEGORIES = _cats([
    ("small_farmer", "Small Farmer 70 %", "70", "regular", "10"),
    ("darkzone_small_farmer", "Darkzone Small Farmer 80%", "80", "regular", "10"),
    ("big_farmer", "Big Farmer 70 %", "70", "regular", "10"),
    ("darkzone_big_farmer", "Darkzone Big Farmer 70 %", "70", "regular", "10"),
    ("sc_st", "SC+ST 85 %", "85", "regular", "5"),
    ("darkzone_sc_st", "Darkzone + SC/ST 90%", "90", "regular", "5"),
    ("seven_year_small", "7 Year Small farmer 55 %", "55", "seven_year", None),
    ("seven_year_big", "7 Year Big Farmer 45%", "45", "seven_year", None),
])

# Sprinkler 'Farmer Share Calculation'!A6:A11 and A19:A20
SPRINKLER_CATEGORIES = _cats([
    ("small_farmer", "Small Farmer 70%", "70", "regular", None),
    ("darkzone_small_farmer", "Small Farmer+Darkzone 80%", "80", "regular", None),
    ("big_farmer", "General Farmer 70%", "70", "regular", None),
    ("darkzone_big_farmer", "General Farmer+Darkzone 70%", "70", "regular", None),
    ("sc_st", "SC+ST (TRIBAL) Farmer 85 %", "85", "regular", None),
    ("darkzone_sc_st", "SC+ST (TRIBAL)+Dark Zone Farmer 90 %", "90", "regular", None),
    ("seven_year_small", "Small Farmer 55%", "55", "seven_year", None),
    ("seven_year_big", "Big Farmer 45%", "45", "seven_year", None),
])

CATEGORIES = {"drip": DRIP_CATEGORIES, "mini_sprinkler": MINI_SPRINKLER_CATEGORIES,
              "sprinkler": SPRINKLER_CATEGORIES}

# Rule 5: Drip 'Quo Summary' has no floor row; Mini I31 and Sprinkler R24 floor at 200.
# Rule 8: Mini M31 pro-rates below 0.2 Ha; Drip does not.
# Rules 14, 15: the 7-year spacing floors, Drip C33 (1.2) and Mini G33 (8).
# Rule 17: GSDMA up to 2 Ha, Mini only.
POLICIES = {
    "drip": SystemPolicy("drip", DRIP_ROUNDING, seven_year_spacing_floor=D("1.2")),
    "mini_sprinkler": SystemPolicy("mini_sprinkler", MINI_SPRINKLER_ROUNDING,
                                   seven_year_spacing_floor=D("8"), inspection_floor=D("200"),
                                   min_area_prorate=True, warn_sump_divergence=True,
                                   gsdma_max_area=D("2")),
    "sprinkler": SystemPolicy("sprinkler", SPRINKLER_ROUNDING, spacing_rule="design",
                              inspection_floor=D("200")),
}

# The Sprinkler line order of BOQ!B16:B23 and the transport line at row 25.
SPRINKLER_COMPONENT_ORDER: tuple[str, ...] = ("pipe", "coupler", "nozzle", "riser", "pcn",
                                              "bend", "tee", "end_plug")


# Two of the workbook's own descriptions carry a line break and a non-breaking
# space. They are the identity of the item in the quantity table, so they are
# kept exactly as the cells hold them.
_NL = chr(10)
_NBSP = chr(160)

# Rule 20: the rates the Sprinkler workbook keeps inside its formulas, transcribed
# with the cell each came from. Descriptions are 'Farmer Share Calculation'!Q60:Q71
# and Q2:Q3; units are BOQ!G16:G25.
_RATES: tuple[tuple[str, int | None, str | None, str, str, str, str], ...] = (
    ("pipe", 75, None, "583.12", "HDPE 17425 SPRINKLER PIPE 75 MM X 2.5 KG WITH SS C CLAMP COUPLER",
     "Mtr.", "BOQ!I16"),
    ("pipe", 90, None, "691.62", "HDPE 17425 SPRINKLER PIPE 90 MM X 2.5 KG WITH SS C CLAMP COUPLER",
     "Mtr.", "BOQ!I16"),
    ("coupler", 75, None, "391.49",
     "Sprinkler Coupler with Foot Batten" + _NL + "Assembly Quick Action 75MM",
     "No.", "BOQ!I17"),
    ("coupler", 90, None, "410.23",
     "Sprinkler Coupler with Foot Batten" + _NL + "Assembly Quick Action 90MM",
     "No.", "BOQ!I17"),
    ("nozzle", None, "plastic", "104.17",
     "Sprinkler Nozzles (1.7 to 2.8 kg/cm2) 5 to 40 Litre/Minute Capacity(Plastic)", "No.",
     "'Farmer Share Calculation'!T3"),
    ("nozzle", None, "brass", "299.23",
     "Sprinkler Nozzles (1.7 to 2.8 kg/cm2) 5 to 40 Litre/Minute Capacity(Brass)", "No.",
     "'Farmer Share Calculation'!T2"),
    ("riser", 75, None, "90.15", "Riser Pipe 20mm Diameter x 75 cm Long", "No.", "BOQ!I19"),
    ("riser", 90, None, "90.15", "Riser Pipe 20mm Diameter x 75 cm Long", "No.", "BOQ!I19"),
    ("pcn", 75, None, "269.04", "SPRINKLER PCN (NIPPLE) 75MM WITH SS C CLAMP", "No.", "BOQ!I20"),
    ("pcn", 90, None, "334", "SPRINKLER PCN (NIPPLE) 90MM WITH SS C CLAMP", "No.", "BOQ!I20"),
    ("bend", 75, None, "282.63", "SPRINKLER BEND 75MM" + _NBSP + " WITH SS C CLAMP", "No.",
     "BOQ!I21"),
    ("bend", 90, None, "294.71", "SPRINKLER BEND 90MM" + _NBSP + " WITH SS C CLAMP", "No.",
     "BOQ!I21"),
    ("tee", 75, None, "303.75", "SPRINKLER TEE 75MM WITH SS C CLAMP", "Mtr.", "BOQ!I22"),
    ("tee", 90, None, "340.21", "SPRINKLER TEE 90MM WITH SS C CLAMP", "Mtr.", "BOQ!I22"),
    ("end_plug", 75, None, "110.97", "SPRINKLER END PLUG 75MM (FOR SPR. C CLAMP PIPE)", "No.",
     "BOQ!I23"),
    ("end_plug", 90, None, "127.18", "SPRINKLER END PLUG 90MM (FOR SPR. C CLAMP PIPE)", "No.",
     "BOQ!I23"),
    ("transport", None, None, "506.45", "Secondary Transportation for SIS", "Set", "BOQ!I25"),
)

SPRINKLER_RATES: tuple[ComponentRate, ...] = tuple(
    ComponentRate(code, desc, uom, D(rate), size, nozzle)
    for code, size, nozzle, rate, desc, uom, _cell in _RATES
)
