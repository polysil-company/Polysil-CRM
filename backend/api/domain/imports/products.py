"""Checking each row of a product import (FS-083).

Pure, like `rows.py`: the service loads the catalogue, the categories, the units
and which HSN codes have a GST rate today, and hands them in.

A row either names a product in the catalogue (an update, or unchanged) or names
none (a new product). Which one follows FS-067 rule 6, in the same order as the
price and line imports, so a sheet means the same product in all three.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from api.domain.imports.cells import CellError, key, name_key, tidy_name, to_bool, to_decimal
from api.domain.imports.reader import SheetRow
from api.domain.imports.rows import (
    NAME_IN_CODE,
    ProductLookups,
    ProductRef,
    RowResult,
    _Ambiguous,
    _get,
)

HSN_RE = re.compile(r"^[0-9]{4,8}$")
MAX_PACK = Decimal("9999999.999")     # numeric(10,3)
MAX_MRP = Decimal("999999999999.99")  # numeric(14,2)
QUOTATION = {"head": "head", "headunit": "head", "field": "field", "both": "both"}
# FS-010 rule 2: a Marketing product is not micro-irrigation equipment
NOT_ELIGIBLE_CATEGORIES = frozenset({key("Marketing")})
_ACTIVE = {"active": True, "inactive": False, "discontinued": False, "retired": False}
# the provisional marks a re-stated value confirms (EC-10)
_PROVISIONAL = {"mrp": ("mrp",), "pack_multiple": ("pack_multiple",),
                "hsn_code": ("hsn_code", "gst_slab")}

# The columns a row may change, in preview order.
CHANGEABLE = ("description", "item_code", "product_category", "quotation_category", "uom",
              "hsn_code", "mrp", "pack_multiple", "is_subsidy_eligible", "is_active")
UNIT_CHANGE = ("a unit change is not imported: stock and open documents are counted in "
               "the old unit. Change it on the product page.")


@dataclass(frozen=True)
class Master:
    """A category or a unit: its id and the code the API shows."""
    id: str
    code: str


@dataclass(frozen=True)
class Current:
    """What the catalogue holds for one product today."""
    ref: ProductRef
    category: Master
    quotation_category: str
    uom: Master
    mrp: Decimal | None
    pack_multiple: Decimal | None
    is_subsidy_eligible: bool
    hsn_code: str | None
    hsn_from: dt.date | None       # the start of the HSN row in force today
    hsn_later: bool                 # a row starting after today exists
    provisional: frozenset[str] = frozenset()


@dataclass
class CatalogueLookups:
    products: ProductLookups
    current: dict[str, Current]                 # product id
    categories: dict[str, Master]               # key(code) and key(name)
    uoms: dict[str, Master]                     # key(code) and key(name)
    rated_hsn: frozenset[str]                   # a GST rate in force today
    today: dt.date
    # name_key of each description and item code to the product holding it, deleted
    # products included: the unique indexes cover them (rule 8)
    descriptions: dict[str, str] = field(default_factory=dict)
    codes: dict[str, str] = field(default_factory=dict)
    deleted: frozenset[str] = frozenset()       # ids of deleted products


def _dec(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


def _identify(r: SheetRow, mapping: Mapping[str, int], lk: ProductLookups,
              res: RowResult) -> tuple[ProductRef | None, str, str]:
    """Rule 1. The product the row names, or None for a new one; and the row's
    tidied code and description. An error leaves `res.errors` set. An existing
    code is never changed (GAP-566)."""
    code = tidy_name(_get(r, mapping, "item_code"))
    desc = tidy_name(_get(r, mapping, "description"))
    if not code and not desc:
        res.errors["item_code" if "item_code" in mapping else "description"] = "required"
        return None, code, desc
    by_code = lk.code(code) if code else None
    by_desc = lk.description(desc) if desc else None
    if isinstance(by_code, _Ambiguous):
        res.errors["item_code"] = f"more than one product has the item code {code!r}"
        return None, code, desc
    if by_code is not None:
        if isinstance(by_desc, ProductRef) and by_desc.id != by_code.id:
            res.errors["description"] = "names a different product from the item code"
            return None, code, desc
        res.matched_on = "item_code"
        return by_code, code, desc
    if isinstance(by_desc, _Ambiguous):
        res.errors["description"] = f"more than one product has the name {desc!r}"
        return None, code, desc
    if by_desc is not None:
        if code and by_desc.item_code:
            res.errors["item_code"] = (f"{code!r} is not this product's item code "
                                       f"({by_desc.item_code})")
            return None, code, desc
        res.matched_on = "description"
        return by_desc, code, desc
    if code and lk.description(code) is not None:
        res.errors["item_code"] = NAME_IN_CODE
    return None, code, desc


def _master(res: RowResult, name: str, text: str, table: dict[str, Master],
            what: str) -> Master | None:
    if not text:
        return None
    found = table.get(key(text))
    if found is None:
        res.errors[name] = f"no {what} {text!r}"
    return found


def parse_products(rows: Sequence[SheetRow], mapping: Mapping[str, int],
                   lk: CatalogueLookups) -> list[RowResult]:
    out: list[RowResult] = []
    for r in rows:
        res = RowResult(r.row)
        product, code, desc = _identify(r, mapping, lk.products, res)
        if res.errors:
            out.append(res)
            continue
        cur = lk.current.get(product.id) if product else None
        new: dict[str, Any] = {}     # field to the value the row asks for

        if cur is None:
            if not desc:
                res.errors["description"] = "required for a new product"
            new["description"] = desc
        elif (res.matched_on == "item_code" and desc
              and name_key(desc) != name_key(cur.ref.description)):
            # rules 4 and EC-8: only a code match renames, and a change of case or
            # spacing alone is not a rename
            new["description"] = desc
        if new.get("description") and not 3 <= len(new["description"]) <= 200:
            res.errors["description"] = "3 to 200 characters"
        if code and (cur is None or not cur.ref.item_code):
            if len(code) > 50:
                res.errors["item_code"] = "at most 50 characters"
            new["item_code"] = code

        category = _master(res, "product_category", _get(r, mapping, "product_category"),
                           lk.categories, "category")
        if category:
            new["product_category"] = category
        qc_text = _get(r, mapping, "quotation_category")
        if qc_text:
            qc = QUOTATION.get(key(qc_text))
            if qc is None:
                res.errors["quotation_category"] = f"{qc_text!r} is not head, field or both"
            else:
                new["quotation_category"] = qc
        unit = _master(res, "uom", _get(r, mapping, "uom"), lk.uoms, "unit")
        if unit:
            if cur is not None and unit.id != cur.uom.id:
                res.errors["uom"] = UNIT_CHANGE   # EC-4, GAP-560
            new["uom"] = unit

        # EC-16: `3917.23.90` and `3917 23 90` are the same code
        hsn = re.sub(r"[\s.]", "", _get(r, mapping, "hsn_code"))
        if hsn:
            if not HSN_RE.match(hsn):
                res.errors["hsn_code"] = f"{hsn!r} is not 4 to 8 digits"
            elif hsn not in lk.rated_hsn:
                res.errors["hsn_code"] = (f"HSN {hsn} has no GST rate in force today. Add the "
                                          f"rate under tax rates first.")
            elif cur is None or cur.hsn_code != hsn:
                if cur is not None and cur.hsn_later:
                    res.errors["hsn_code"] = ("this product has a later HSN change already. "
                                              "Change it on the product page.")
                elif cur is not None and cur.hsn_from == lk.today:
                    res.errors["hsn_code"] = ("this product's HSN was set today already. "
                                              "Change it on the product page.")
                else:
                    new["hsn_code"] = hsn
            else:
                new["hsn_code"] = hsn

        for name, places, most in (("mrp", 2, MAX_MRP), ("pack_multiple", 3, MAX_PACK)):
            text = _get(r, mapping, name)
            if text:
                try:
                    new[name] = to_decimal(text, places=places, minimum=Decimal(0),
                                           maximum=most, exclusive_min=True)
                except CellError as exc:
                    res.errors[name] = str(exc)
        for name in ("is_subsidy_eligible", "is_active"):
            text = _get(r, mapping, name)
            if text:
                if name == "is_active" and key(text) in _ACTIVE:
                    new[name] = _ACTIVE[key(text)]
                    continue
                try:
                    new[name] = to_bool(text)
                except CellError as exc:
                    res.errors[name] = str(exc)

        # rule 7, and EC-15 for a product moved into Marketing
        cat = new.get("product_category")
        if (cat is not None and "is_subsidy_eligible" not in new
                and key(cat.code) in NOT_ELIGIBLE_CATEGORIES
                and (cur is None or key(cur.category.code) not in NOT_ELIGIBLE_CATEGORIES)):
            new["is_subsidy_eligible"] = False

        if cur is None:
            for name, label in (("product_category", "category"),
                                ("quotation_category", "quotation category"), ("uom", "unit")):
                if name not in new:
                    res.errors.setdefault(name, f"a new product needs a {label}")
        if res.errors:
            out.append(res)
            continue
        _settle(res, product, cur, new)
        out.append(res)
    _cross_check(out, lk)
    return out


def _now(cur: Current, name: str) -> Any:
    return {"description": cur.ref.description, "item_code": cur.ref.item_code,
            "product_category": cur.category, "quotation_category": cur.quotation_category,
            "uom": cur.uom, "hsn_code": cur.hsn_code, "mrp": cur.mrp,
            "pack_multiple": cur.pack_multiple, "is_subsidy_eligible": cur.is_subsidy_eligible,
            "is_active": cur.ref.is_active}[name]


def _show(v: Any) -> Any:
    if isinstance(v, Master):
        return v.code
    if isinstance(v, Decimal):
        return format(v, "f")
    return v


def _settle(res: RowResult, product: ProductRef | None, cur: Current | None,
            new: dict[str, Any]) -> None:
    """The row's action, its changes, and the record commit writes."""
    v = res.values
    if cur is None or product is None:
        category = new["product_category"]
        v.update(action="new", product_id=None, product=new["description"],
                 item_code=new.get("item_code"), changes={})
        v["write"] = {
            "description": new["description"], "item_code": new.get("item_code"),
            "category_id": category.id, "quotation_category": new["quotation_category"],
            "uom_id": new["uom"].id, "hsn_code": new.get("hsn_code"),
            "mrp": _dec(new.get("mrp")), "pack_multiple": _dec(new.get("pack_multiple")),
            "is_subsidy_eligible": new.get("is_subsidy_eligible", True),
            "is_active": new.get("is_active", True)}
        return
    changes: dict[str, dict[str, Any]] = {}
    confirms: list[str] = []
    for name in CHANGEABLE:
        if name not in new:
            continue
        before = _now(cur, name)
        after = new[name]
        same = (isinstance(before, Master) and before.id == after.id) if isinstance(
            after, Master) else before == after
        if not same:
            changes[name] = {"from": _show(before), "to": _show(after)}
        elif name in _PROVISIONAL and cur.provisional & set(_PROVISIONAL[name]):
            # EC-10, GAP-562: the client's sheet stating our stand-in confirms it
            confirms.extend(m for m in _PROVISIONAL[name] if m in cur.provisional)
            changes[name] = {"from": _show(before), "to": _show(after), "confirmed": True}
    final = new["description"] if "description" in changes else cur.ref.description
    v.update(action="update" if changes else "unchanged", product_id=product.id,
             product=final, item_code=new["item_code"] if "item_code" in changes
             else cur.ref.item_code, changes=changes)
    if not cur.ref.is_active and new.get("is_active") is not True:
        res.notes["is_active"] = "switched off"   # EC-9
    if changes:
        # only the changed columns; null keeps the catalogue's value at commit, so a
        # field edited on the product page meanwhile is not overwritten
        w: dict[str, Any] = {"id": product.id, "confirm": confirms}
        for name, change in changes.items():
            if change.get("confirmed"):
                continue
            after = new[name]
            column = {"product_category": "category_id", "uom": "uom_id"}.get(name, name)
            w[column] = after.id if isinstance(after, Master) else (
                _dec(after) if isinstance(after, Decimal) else after)
        v["write"] = w


def _cross_check(results: list[RowResult], lk: CatalogueLookups) -> None:
    """Rule 8: one row per product, and no description or item code that another
    product holds or another row ends with. Compared by `name_key` (EC-1): two
    names that differ only in spacing would make every later import by name
    ambiguous. A deleted product still holds its name (GAP-565)."""
    good = [r for r in results if r.ok]
    first: dict[tuple[str, str], int] = {}
    clash: dict[int, dict[str, str]] = {}

    def note(res: RowResult, name: str, msg: str) -> None:
        clash.setdefault(res.row, {}).setdefault(name, msg)

    for res in good:
        v = res.values
        where = res.matched_on or "description"
        if v["product_id"]:
            k = ("id", v["product_id"])
            if k in first:
                note(res, where, f"the same product as row {first[k]}")
                other = next(o for o in good if o.row == first[k])
                note(other, other.matched_on or "description",
                     f"the same product as row {res.row}")
            else:
                first[k] = res.row
        w = v.get("write") or {}
        for name in ("description", "item_code"):
            value = w.get(name)
            if not value:
                continue
            folded = name_key(str(value))
            holder = (lk.descriptions if name == "description" else lk.codes).get(folded)
            if holder is not None and holder != v["product_id"]:
                note(res, name, "a deleted product has this " + name.replace("_", " ")
                     if holder in lk.deleted else
                     "another product has this " + name.replace("_", " "))
            k = (name, folded)
            if k in first and first[k] != res.row:
                note(res, name, f"also on row {first[k]}")
                other = next(o for o in good if o.row == first[k])
                note(other, name, f"also on row {res.row}")
            else:
                first.setdefault(k, res.row)
    for res in good:
        for name, msg in clash.get(res.row, {}).items():
            res.errors.setdefault(name, msg)


def change_counts(results: Sequence[RowResult]) -> dict[str, int]:
    """EC-7: what the good rows do, so a rename or a switch-off past the preview's
    twentieth row is still seen before saving."""
    good = [r for r in results if r.ok]
    counts = {a: sum(1 for r in good if r.values["action"] == a)
              for a in ("new", "update", "unchanged")}
    changes = [r.values["changes"] for r in good if r.values["action"] == "update"]
    counts["renamed"] = sum(1 for c in changes if "description" in c)
    counts["switched_off"] = sum(1 for c in changes if c.get("is_active", {}).get("to") is False)
    counts["switched_on"] = sum(1 for c in changes if c.get("is_active", {}).get("to") is True)
    counts["hsn_changed"] = sum(1 for c in changes
                                if "hsn_code" in c and not c["hsn_code"].get("confirmed"))
    counts["still_off"] = sum(1 for r in good if r.notes.get("is_active"))
    return counts


def preview_order(res: RowResult) -> int:
    """EC-7: renames and switch-offs first, then the rest in sheet order."""
    c = res.values.get("changes") or {}
    return 0 if "description" in c or c.get("is_active", {}).get("to") is False else 1


def fingerprint(results: Sequence[RowResult]) -> str:
    """What saving would do, row by row, and which rows fail (plan review N-2)."""
    good = sorted((r.row, r.values["action"], r.values["product_id"], r.values["changes"])
                  for r in results if r.ok)
    bad = sorted(r.row for r in results if not r.ok)
    blob = json.dumps([good, bad], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
