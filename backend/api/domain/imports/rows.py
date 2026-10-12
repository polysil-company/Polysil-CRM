"""Checking each row of an import against its kind's rules (FS-062 section 4).

Pure: the service loads the lookups (states, districts, products, which codes are
taken, which territories are outside the caller's area) and hands them in. Every
row gets every error it has, so a sheet is fixed in one pass, not one error per
round trip.

Values leave here as JSON-ready text, in the stored form: a mobile as
`91XXXXXXXXXX`, money with two decimals.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from api.domain import identity
from api.domain.imports.cells import CellError, key, to_bool, to_decimal
from api.domain.imports.reader import SheetRow

TYPE_ORDER = ("distributor", "dealer", "sub_dealer")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MAX_QTY = Decimal("1000000")
HUNDRED = Decimal(100)

_TYPES = {"distributor": "distributor", "dist": "distributor", "d": "distributor",
          "dealer": "dealer", "subdealer": "sub_dealer", "sd": "sub_dealer",
          "sub": "sub_dealer", "retailer": "sub_dealer"}


@dataclass
class RowResult:
    row: int
    values: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _get(r: SheetRow, mapping: Mapping[str, int], name: str) -> str:
    i = mapping.get(name)
    return r.cells[i].strip() if i is not None and i < len(r.cells) else ""


def _length(res: RowResult, name: str, value: str, most: int) -> str | None:
    if len(value) > most:
        res.errors[name] = f"at most {most} characters"
        return None
    return value or None


# ── partners ─────────────────────────────────────────────────────────────────

@dataclass
class Place:
    id: str
    name: str


@dataclass
class PartnerLookups:
    states: dict[str, Place]                       # key(name) and key(code) -> state
    districts: dict[tuple[str, str], Place]        # (state id, key(name)) -> district


def parse_partners(rows: Sequence[SheetRow], mapping: Mapping[str, int],
                   lk: PartnerLookups) -> list[RowResult]:
    """Formats and lookups that need no knowledge of other rows or of scope."""
    out = []
    for r in rows:
        res = RowResult(r.row)
        v = res.values
        raw_type = _get(r, mapping, "partner_type")
        ptype = _TYPES.get(key(raw_type))
        if not raw_type:
            res.errors["partner_type"] = "required"
        elif ptype is None:
            res.errors["partner_type"] = f"{raw_type!r} is not distributor, dealer or sub-dealer"
        v["partner_type"] = ptype

        code = _get(r, mapping, "code")
        if not code:
            res.errors["code"] = "required"
        v["code"] = _length(res, "code", code, 32)
        name = _get(r, mapping, "name")
        if not name:
            res.errors["name"] = "required"
        v["name"] = _length(res, "name", name, 200)

        state_text = _get(r, mapping, "state")
        state = lk.states.get(key(state_text)) if state_text else None
        if not state_text:
            res.errors["state"] = "required"
        elif state is None:
            res.errors["state"] = f"no state {state_text!r}"
        district_text = _get(r, mapping, "district")
        district = None
        if district_text and state is not None:
            district = lk.districts.get((state.id, key(district_text)))
            if district is None:
                res.errors["district"] = f"no district {district_text!r} in {state.name}"
        place = district or state
        v["territory_id"] = place.id if place else None
        v["territory"] = (f"{district.name}, {state.name}" if district and state
                          else state.name if state else None)
        v["territory_field"] = "district" if district else "state"

        parent = _get(r, mapping, "parent_code")
        v["parent_code"] = _length(res, "parent_code", parent, 32)
        v["contact_name"] = _length(res, "contact_name", _get(r, mapping, "contact_name"), 200)
        v["address"] = _length(res, "address", _get(r, mapping, "address"), 1000)

        mobile = _get(r, mapping, "mobile")
        v["mobile"] = None
        if mobile:
            try:
                v["mobile"] = identity.mobile_for_user(mobile)
            except identity.MobileError:
                res.errors["mobile"] = "not an Indian mobile number"
        email = _get(r, mapping, "email")
        v["email"] = None
        if email:
            try:
                v["email"] = identity.normalise_email(email)
            except identity.EmailError:
                res.errors["email"] = "not an email"
        gstin = _get(r, mapping, "gstin").upper().replace(" ", "")
        v["gstin"] = None
        if gstin:
            if GSTIN_RE.match(gstin):
                v["gstin"] = gstin
            else:
                res.errors["gstin"] = "not a GSTIN"
        pan = _get(r, mapping, "pan").upper().replace(" ", "")
        v["pan"] = None
        if pan:
            if PAN_RE.match(pan):
                v["pan"] = pan
            else:
                res.errors["pan"] = "not a PAN"
        registered_text = _get(r, mapping, "is_gst_registered")
        registered = bool(gstin)
        if registered_text:
            try:
                registered = to_bool(registered_text)
            except CellError as exc:
                res.errors["is_gst_registered"] = str(exc)
        if registered and not gstin and "is_gst_registered" not in res.errors:
            res.errors["gstin"] = "required when GST registered"
        v["is_gst_registered"] = registered

        v["credit_limit"] = None
        credit = _get(r, mapping, "credit_limit")
        if credit:
            try:
                v["credit_limit"] = str(to_decimal(credit, places=2, minimum=Decimal(0)))
            except CellError as exc:
                res.errors["credit_limit"] = str(exc)
        v["payment_terms_days"] = None
        terms = _get(r, mapping, "payment_terms_days")
        if terms:
            try:
                v["payment_terms_days"] = int(to_decimal(terms, places=0, minimum=Decimal(0),
                                                         maximum=Decimal(365)))
            except CellError as exc:
                res.errors["payment_terms_days"] = str(exc)
        out.append(res)

    _duplicates(out, "code", lambda v: (v.get("code") or "").casefold() or None)
    return out


def finish_partners(results: list[RowResult], *, taken: set[str], outside: set[str],
                    existing: Mapping[str, tuple[str, str]],
                    skipped: frozenset[int] = frozenset()) -> None:
    """The checks that need the database's answers or the other rows.

    `taken`: casefolded codes already in use anywhere. `outside`: territory ids the
    caller may not place a partner in. `existing`: casefolded code to (id, type) of
    partners the caller can see. `skipped`: rows the person chose not to import.

    Rows are settled in type order, so a dealer under a distributor with errors
    gets an error of its own (EC-12): importing "good rows only" would otherwise
    strand it at commit.
    """
    for res in results:
        v = res.values
        # GAP-471: a code in use is an error, never an update of that partner
        if v.get("code") and v["code"].casefold() in taken:
            res.errors.setdefault("code", f"{v['code']} is already in use")
        if v.get("territory_id") in outside:
            res.errors.setdefault(v["territory_field"], f"{v['territory']} is outside your area")

    in_file: dict[str, RowResult] = {}
    for res in results:
        code = res.values.get("code")
        if code and code.casefold() not in in_file:
            in_file[code.casefold()] = res

    def rank(res: RowResult) -> int:
        t = res.values.get("partner_type")
        return TYPE_ORDER.index(t) if t in TYPE_ORDER else len(TYPE_ORDER)

    for res in sorted(results, key=rank):
        parent_code = res.values.get("parent_code")
        ptype = res.values.get("partner_type")
        res.values["parent_row"] = None
        res.values["parent_id"] = None
        if not parent_code or ptype not in TYPE_ORDER:
            continue
        expected = TYPE_ORDER[TYPE_ORDER.index(ptype) - 1] if ptype != "distributor" else None
        found = in_file.get(parent_code.casefold())
        if found is res:
            res.errors.setdefault("parent_code", "a partner cannot be its own parent")
            continue
        if found is not None:
            if found.values.get("partner_type") != expected:
                res.errors.setdefault("parent_code", _wrong_type(ptype))
            elif not found.ok or found.row in skipped:
                res.errors.setdefault("parent_code", f"the parent on row {found.row} has errors")
            else:
                res.values["parent_row"] = found.row
            continue
        known = existing.get(parent_code.casefold())
        if known is None:
            res.errors.setdefault("parent_code", f"no partner with code {parent_code}")
        elif known[1] != expected:
            res.errors.setdefault("parent_code", _wrong_type(ptype))
        else:
            res.values["parent_id"] = known[0]


def _wrong_type(ptype: str) -> str:
    if ptype == "distributor":
        return "a distributor has no parent"
    return "wrong type for this parent: the order is distributor > dealer > sub-dealer"


# ── products: price items and lines ──────────────────────────────────────────

@dataclass
class ProductRef:
    id: str
    description: str
    is_active: bool
    uom_code: str
    uom_decimals: int
    pack_multiple: Decimal | None


@dataclass
class ProductLookups:
    by_code: dict[str, ProductRef]            # casefolded item code
    by_description: dict[str, ProductRef]     # casefolded description


def _product(r: SheetRow, mapping: Mapping[str, int], lk: ProductLookups,
             res: RowResult) -> ProductRef | None:
    code = _get(r, mapping, "item_code")
    desc = _get(r, mapping, "description")
    if not code and not desc:
        res.errors["item_code" if "item_code" in mapping else "description"] = "required"
        return None
    # GAP-473: exact item code or exact description only, no closest match
    by_code = lk.by_code.get(code.casefold()) if code else None
    by_desc = lk.by_description.get(desc.casefold()) if desc else None
    if code and by_code is None:
        res.errors["item_code"] = f"no product with item code {code}"
        return None
    if by_code and by_desc and by_code.id != by_desc.id:
        # EC-17. A description that matches nothing is ignored when the code matches:
        # sheets carry their own wording.
        res.errors["description"] = "names a different product from the item code"
        return None
    found = by_code or by_desc
    if found is None:
        res.errors["description"] = f"no product {desc!r}"
        return None
    res.values["product_id"] = found.id
    res.values["product"] = found.description
    return found


def parse_price_items(rows: Sequence[SheetRow], mapping: Mapping[str, int],
                      lk: ProductLookups) -> list[RowResult]:
    out = []
    for r in rows:
        res = RowResult(r.row)
        _product(r, mapping, lk, res)
        rate = _get(r, mapping, "rate")
        if not rate:
            res.errors["rate"] = "required"
        else:
            try:
                res.values["rate"] = str(to_decimal(rate, places=2, minimum=Decimal(0),
                                                    exclusive_min=True))
            except CellError as exc:
                res.errors["rate"] = str(exc)
        out.append(res)
    _duplicates(out, "item_code" if "item_code" in mapping else "description",
                lambda v: v.get("product_id"))
    return out


def parse_lines(rows: Sequence[SheetRow], mapping: Mapping[str, int],
                lk: ProductLookups) -> list[RowResult]:
    out = []
    for r in rows:
        res = RowResult(r.row)
        product = _product(r, mapping, lk, res)
        if product is not None and not product.is_active:
            res.errors["item_code" if "item_code" in mapping else "description"] = (
                "this product is no longer sold")
        qty = _get(r, mapping, "qty")
        if not qty:
            res.errors["qty"] = "required"
        else:
            places = product.uom_decimals if product else 3
            try:
                q = to_decimal(qty, places=places, minimum=Decimal(0), maximum=MAX_QTY,
                               exclusive_min=True)
                if product and product.pack_multiple and q % product.pack_multiple != 0:
                    res.errors["qty"] = (f"sold in multiples of {product.pack_multiple:f} "
                                         f"{product.uom_code}")
                res.values["qty"] = format(q, "f")
            except CellError as exc:
                msg = str(exc)
                if product and ("decimal" in msg or "whole number" in msg):
                    msg = f"{product.uom_code} takes {places} decimal places"
                res.errors["qty"] = msg
        for name in ("discount_pct", "discount2_pct", "discount3_pct"):
            text = _get(r, mapping, name)
            res.values[name] = "0"
            if text:
                try:
                    res.values[name] = format(to_decimal(text, places=3, minimum=Decimal(0),
                                                         maximum=HUNDRED), "f")
                except CellError as exc:
                    res.errors[name] = str(exc)
        out.append(res)
    return out


def _duplicates(results: list[RowResult], field_name: str,
                ident: Any) -> None:
    first: dict[Any, int] = {}
    for res in results:
        k = ident(res.values)
        if k is None:
            continue
        if k in first:
            res.errors.setdefault(field_name, f"also on row {first[k]}")
        else:
            first[k] = res.row
    # the first row of a repeated value is also wrong: which one was meant?
    repeated = {ident(res.values) for res in results
                if res.errors.get(field_name, "").startswith("also on row")}
    for res in results:
        k = ident(res.values)
        if k in repeated and first.get(k) == res.row:
            later = next(o.row for o in results if o.row != res.row and ident(o.values) == k)
            res.errors.setdefault(field_name, f"also on row {later}")
