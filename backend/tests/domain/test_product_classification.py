"""The stand-in tax classification, and the two traps in it (FS-010 rule 10).

No database: these test the loader's pure functions against the descriptions that
actually appear in the client's file.

Both cases below were found by reading what the rules matched rather than by
reasoning about them, and **one of them produced the right tax for the wrong
reason**, which is the kind that survives a review.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.load_product_master import hsn_for, normalise, stand_in_rate

D = Decimal


# ── the `SERVIC` trap ────────────────────────────────────────────────────────

@pytest.mark.parametrize("description", [
    'SERVICE SADDLE 63X1"', 'SERVICE SADDLE 75X1"',
    'SERVICE SADDLE 90X1"', 'SERVICE SADDLE 110X1"',
])
def test_a_service_saddle_is_a_fitting_not_a_service(description: str) -> None:
    """Four of the five descriptions containing `SERVIC` are plastic fittings at
    5 %. A keyword rule without the exception, ordered the other way, taxes all
    four as services at 18 %."""
    assert hsn_for(description, "DRIP COMPONENTS") == "3926"


def test_the_one_actual_service_is_taxed_as_one() -> None:
    assert hsn_for("7.5 HP MOTAR SERVICS", "HDPE SPRINKLER SYSTEM") == "9995"


# ── the `CAP` trap, which produced the right tax for the wrong reason ────────

@pytest.mark.parametrize("description", [
    "END CAP QPC (HDPE) 110MM", "CAP FOR EMITTER 4LPH",
    "COMP.END CAP 32MM", 'END CAP O RING 3.0"', "COLLECTOR CAP GASKET FOR HYDROCYCLON",
])
def test_a_pipe_end_cap_is_not_headwear(description: str) -> None:
    """Applied across the whole catalogue, `CAP` classified seventeen fittings
    under the code for hats. **Both codes carry 5 %**, so every figure on every
    document was correct and nothing looked wrong; what was wrong was the code
    printed on a tax invoice. Marketing keywords are consulted only for Marketing
    products, which is the rule this asserts."""
    assert hsn_for(description, "DRIP COMPONENTS") != "6505"


def test_the_company_cap_is_headwear() -> None:
    assert hsn_for("POLYSIL CAP", "Marketing") == "6505"


def test_a_diary_with_a_pen_is_a_diary() -> None:
    """Order inside the marketing table: whichever a person ordering it would
    call it."""
    assert hsn_for("POLYSIL DIARY-BIG WITH PEN", "Marketing") == "4820"
    assert hsn_for("POLYSIL PEN", "Marketing") == "9608"


@pytest.mark.parametrize(("description", "code"), [
    ("POLYSIL UMBRELLA", "6601"), ("POLYSIL NON WOVEN BAG", "6305"),
    ("POLYSIL COMPANY PROFILE-LITERACHURE", "4911"),
])
def test_the_marketing_items_get_marketing_codes(description: str, code: str) -> None:
    assert hsn_for(description, "Marketing") == code


# ── the ordinary cases ───────────────────────────────────────────────────────

@pytest.mark.parametrize(("description", "category", "code"), [
    ("UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985", "PVC PIPES", "3917"),
    ("EMITTING 12-4-CL-2-30", "EMITTING PIPE", "3917"),
    ("HDPE PIPE PE100 110MMX", "HDPE PIPES", "3917"),
    ('AIR RELEASE VALVE 1"', "DRIP COMPONENTS", "8481"),
    ("PLASTIC DISC FILTER DOUBLE ELEMENT", "DRIP COMPONENTS", "8424"),
    ("Sprinkler Nozzles (1.7 to 2.8 kg/cm2)", "SPRINKLER COMPONENTS", "8424"),
    ("20MM STRAIGHT CONNECTOR/JOINER (N )", "DRIP COMPONENTS", "3926"),
])
def test_the_catalogue_classifies_the_way_the_category_says(
        description: str, category: str, code: str) -> None:
    assert hsn_for(description, category) == code


# ── the client's whitespace ──────────────────────────────────────────────────

def test_a_stored_carriage_return_comes_off_before_the_trim() -> None:
    """openpyxl renders it as seven literal characters. A plain strip removes the
    newline and leaves them, which is a distinct value that passes every
    constraint and then prints on a quotation."""
    raw = "FLAT EMITTING 16-2-CL-2-50 (200MTR)_x000D_\n"
    assert normalise(raw) == "FLAT EMITTING 16-2-CL-2-50 (200MTR)"
    assert raw.strip() != normalise(raw), "a naive strip is not enough, which is the point"


@pytest.mark.parametrize("raw", [
    "POLYFLEX CONNECTOR 16MM\t", "POLYFLEX CONNECTOR 16MM ",
    "POLYFLEX CONNECTOR 16MM\r\n", "POLYFLEX CONNECTOR 16MM\u00a0",
    "POLYFLEX  CONNECTOR  16MM",
])
def test_every_kind_of_whitespace_normalises_to_one_value(raw: str) -> None:
    assert normalise(raw) == "POLYFLEX CONNECTOR 16MM"


# ── the stand-in rates ───────────────────────────────────────────────────────

def test_a_stand_in_rate_is_stable_for_a_product() -> None:
    """Deterministic, so a rerun does not churn every rate in the catalogue."""
    first = stand_in_rate("UPVC PIPE 90 MM", "PVC PIPES")
    assert first == stand_in_rate("UPVC PIPE 90 MM", "PVC PIPES")


@pytest.mark.parametrize(("category", "low", "high"), [
    ("PVC PIPES", "45.00", "410.00"), ("EMITTING PIPE", "8.00", "26.00"),
    ("DRIP COMPONENTS", "1.50", "320.00"), ("Marketing", "25.00", "900.00"),
])
def test_a_stand_in_rate_sits_in_its_category_band(category: str, low: str, high: str) -> None:
    """The bands come from the BOQ workbooks' own observed ranges, so the figures
    are the right order of magnitude even though they are invented."""
    for name in ("A", "SOME PRODUCT", "ZZZZ 110MM PN 6", "X" * 40):
        rate = stand_in_rate(name, category)
        assert D(low) <= rate <= D(high), (category, name, rate)
        assert rate > 0, "the column refuses a rate of zero or below"
