"""The GST registrations loader's own checks (scripts/load_seller_gstins.py): the
check digit catches a mistyped GSTIN before it reaches a quotation, and the CSV
must name exactly one default."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.load_seller_gstins import check_digit, read_rows

HEAD = "state_code,state_name,gstin,legal_name,address,effective_from,is_default,source\n"


# two registrations published as worked examples, so the algorithm is checked against
# digits it did not produce; the client's own GSTINs stay out of the shared repository
@pytest.mark.parametrize("gstin", ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"])
def test_the_check_digit_of_published_registrations(gstin: str) -> None:
    assert check_digit(gstin) == gstin[14]


def test_a_mistyped_gstin_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "g.csv"
    f.write_text(HEAD + "GJ,Gujarat,24AAACP1234A1ZC,P,A,2017-07-01,true,x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="check digit"):
        read_rows(f)


@pytest.mark.parametrize("defaults", ["false,false", "true,true"])
def test_exactly_one_default(tmp_path: Path, defaults: str) -> None:
    a, b = defaults.split(",")
    f = tmp_path / "g.csv"
    rows = (f"GJ,Gujarat,24AAACP1234A1ZB,P,A,2017-07-01,{a},x\n"
            f"UP,Uttar Pradesh,09AAACP1234A1Z3,P,A,2023-12-22,{b},x\n")
    f.write_text(HEAD + rows, encoding="utf-8")
    with pytest.raises(SystemExit, match="exactly one"):
        read_rows(f)
