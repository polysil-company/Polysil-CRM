"""A made-up quotation, in the shape the render claim hands the job (FS-005 5.3,
FS-064), and the figures its first page must carry.

Shared by the render tests and the box checks (FS-065 rule 5), so the document
the suite proves is the one a deployed worker renders. No row in any database
stands behind it: the ids, the number and the party are invented.
"""

from __future__ import annotations

import copy
from typing import Any

LINE: dict[str, Any] = {
    "line_no": 1, "description": "UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985",
    "hsn_code": "3917", "uom": "MTR", "qty": "18.000", "rate": "103.19",
    "gross": "1857.42", "discount_pct": "10.000", "discount1_amt": "185.74",
    "after_discount1": "1671.68", "discount2_pct": "5.000", "discount2_amt": "83.58",
    "after_discount2": "1588.10", "discount3_pct": "0.000", "discount3_amt": "0.00",
    "discount": "269.32", "taxable": "1588.10", "gst_slab": "5.000",
    "cgst_rate": "2.500", "sgst_rate": "2.500", "igst_rate": "0.000",
    "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50",
}
# a second line with figures of its own, so no line figure equals a document
# total: with one line the totals rows satisfied every line assertion, and a
# blank or swapped line cell passed (FS-064 code review F-1)
LINE_2: dict[str, Any] = {
    "line_no": 2, "description": "END PLUG WITH QUICK ACTION COUPLER 90MM",
    "hsn_code": "3917", "uom": "NOS", "qty": "4.000", "rate": "50.00",
    "gross": "200.00", "discount_pct": "10.000", "discount1_amt": "20.00",
    "after_discount1": "180.00", "discount2_pct": "0.000", "discount2_amt": "0.00",
    "after_discount2": "180.00", "discount3_pct": "0.000", "discount3_amt": "0.00",
    "discount": "20.00", "taxable": "180.00", "gst_slab": "5.000",
    "cgst_rate": "2.500", "sgst_rate": "2.500", "igst_rate": "0.000",
    "cgst": "4.50", "sgst": "4.50", "igst": "0.00", "total": "189.00",
}
PRINT: dict[str, Any] = {
    "dealer_name": "Shree Agro", "dealer_contact": "Bhavesh Shah", "dealer_mobile": "9876500000",
    "village": "Vadod", "taluka": "Gondal", "district": "Rajkot", "state": "Gujarat",
    "supply_state": "Gujarat", "mis_system": "Sprinkler", "made_by": "Ravi Kumar",
}

QUOTE_NO = "QT/GJ/2026-27/00001"

# Each line's price, price after discount, discount and total, then the sub total
# and the grand total: none equals another, so a blank or swapped cell is missed.
PAGE_ONE_FIGURES: tuple[str, ...] = (
    "103.19", "88.23", "269.32", "1,588.10", "45.00", "180.00", "1,768.10", "1,856.50",
    QUOTE_NO)


def document(*, provisional: bool = False, intra: bool = True, party: str = "Rameshbhai Patel",
             terms: str | None = "Prices ex-works.", lines: int = 2) -> dict[str, Any]:
    """A fresh copy every call: callers change it freely. Past two lines, the
    first line repeats under new numbers."""
    return {
        "quotation": {
            "id": "00000000-0000-0000-0000-000000000001", "quote_no": QUOTE_NO,
            "version": 1, "sales_type": "commercial", "sent_at": "2026-10-01T09:00:00+05:30",
            "valid_until": "2026-11-15", "price_effective_date": "2026-10-03",
            "is_provisional": provisional, "intra_state": intra, "tax_treatment": "domestic",
            "seller_legal_name": "Polysil Irrigation Systems Pvt Ltd",
            "seller_address": "Rajkot, Gujarat", "seller_gstin_no": "24AAACP1234A1Z5",
            "seller_state_code": "GJ",
            "party_name": party, "party_address": "Near the dairy, Anand road",
            "party_mobile": "+919876543210",
            "party_gstin": None, "terms": terms, "export_country": None, "lut_arn": None,
            "gross": "2057.42", "discount": "289.32", "taxable": "1768.10",
            "cgst": "44.20", "sgst": "44.20", "igst": "0.00", "total": "1856.50",
            "share_token": "t" * 43,
        },
        "lines": [dict(LINE), dict(LINE_2)][:lines]
        + [{**LINE, "line_no": n + 1} for n in range(2, lines)],
        "print": copy.deepcopy(PRINT),
    }
