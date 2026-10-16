"""Each import kind's fields, the column guesses, and the mapping check (FS-062 section 4).

A mapping is `{field key: column index}`. The server only suggests one; the person
decides (rule 2).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from api.domain.imports.cells import key

KINDS = ("partners", "price_list_items", "lines")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    required: bool
    help: str
    aliases: tuple[str, ...] = ()
    # FS-068: the template's sheet 2 example, made up and easy to spot
    example: str = ""
    # FS-068 rule 5: a code column, text-formatted in the template
    text: bool = False


_PRODUCT = (
    FieldSpec("item_code", "Item code", False,
              "The product's item code. Give this or the description.",
              ("itemcode", "code", "sku", "productcode", "partno", "partnumber", "itemno"),
              example="EXAMPLE-1", text=True),
    FieldSpec("description", "Description", False,
              "The product's description, exactly as in the catalogue. Give this or the item "
              "code.", ("description", "product", "productname", "item", "itemname",
                        "itemdescription", "particulars", "name", "productdescription",
                        "desc"), example="EXAMPLE PIPE 16 MM"),
)

FIELDS: dict[str, tuple[FieldSpec, ...]] = {
    "partners": (
        FieldSpec("partner_type", "Type", True,
                  "Distributor, dealer or sub-dealer.",
                  ("type", "partnertype", "category", "dealertype", "level"), example="Dealer"),
        FieldSpec("code", "Code", True, "Unique across all partners.",
                  ("code", "partnercode", "dealercode", "distributorcode", "id"),
                  example="EXAMPLE-1", text=True),
        FieldSpec("name", "Name", True, "The partner's business name.",
                  ("name", "partnername", "dealername", "firmname", "businessname",
                   "distributorname", "firm", "shopname"), example="Example Traders"),
        FieldSpec("state", "State", True, "A state's name or its two-letter code.",
                  ("state", "statename", "statecode"), example="Gujarat"),
        FieldSpec("district", "District", False,
                  "A district in that state. Without one, the partner sits at the state.",
                  ("district", "dist", "districtname", "city"), example="Ahmedabad"),
        FieldSpec("parent_code", "Parent code", False,
                  "The code of the partner one type up: a dealer's distributor, a sub-dealer's "
                  "dealer. It may be a row in this file.",
                  ("parentcode", "parent", "distributor", "distributorcode", "underdealer",
                   "dealer", "under"), example="EXAMPLE-D1", text=True),
        FieldSpec("contact_name", "Contact name", False, "The person to speak to.",
                  ("contactname", "contact", "contactperson", "owner", "ownername",
                   "proprietor", "person"), example="A. Kumar"),
        FieldSpec("mobile", "Mobile", False, "An Indian mobile, in any common form.",
                  ("mobile", "mob", "mobileno", "mobilenumber", "phone", "phoneno", "contactno",
                   "contactnumber", "whatsapp", "cell"), example="9000000001", text=True),
        FieldSpec("email", "Email", False, "An email address.",
                  ("email", "emailid", "mail", "emailaddress"), example="example@example.com"),
        FieldSpec("address", "Address", False, "The full address, in one cell.",
                  ("address", "fulladdress", "addr"), example="12 Example Road, Ahmedabad"),
        FieldSpec("gstin", "GSTIN", False, "15 characters. Needed when GST registered is yes.",
                  ("gstin", "gst", "gstno", "gstnumber", "gstinno"), example="24AAAAA0000A1Z5",
                  text=True),
        FieldSpec("pan", "PAN", False, "10 characters.", ("pan", "panno", "pannumber"),
                  example="AAAAA0000A", text=True),
        FieldSpec("is_gst_registered", "GST registered", False,
                  "Yes or no. Without the column, yes when a GSTIN is given.",
                  ("gstregistered", "registered", "isgstregistered"), example="Yes"),
        FieldSpec("credit_limit", "Credit limit", False, "Rupees, at most two decimals.",
                  ("creditlimit", "credit", "limit"), example="50000"),
        FieldSpec("payment_terms_days", "Payment terms (days)", False, "0 to 365.",
                  ("paymentterms", "paymenttermsdays", "creditdays", "terms", "days"),
                  example="30"),
    ),
    "price_list_items": (
        *_PRODUCT,
        FieldSpec("rate", "Rate", True,
                  "Rupees per unit, more than 0, at most two decimals. More is refused, not "
                  "rounded.", ("rate", "price", "unitprice", "amount", "mrp", "listprice",
                               "unitrate", "netrate"), example="125.50"),
    ),
    "lines": (
        *_PRODUCT,
        FieldSpec("qty", "Quantity", True, "More than 0, in the product's unit.",
                  ("qty", "quantity", "qnty", "nos", "units"), example="10"),
        FieldSpec("discount_pct", "Discount %", False, "0 to 100.",
                  ("discount", "discountpct", "disc", "discountpercent", "discount1"),
                  example="5"),
        FieldSpec("discount2_pct", "Discount 2 %", False, "0 to 100.",
                  ("discount2", "disc2", "discount2pct"), example="2"),
        FieldSpec("discount3_pct", "Discount 3 %", False, "0 to 100.",
                  ("discount3", "disc3", "discount3pct"), example="0"),
    ),
}

# At least one of each group must be mapped.
ONE_OF: dict[str, tuple[tuple[str, ...], ...]] = {
    "partners": (),
    "price_list_items": (("item_code", "description"),),
    "lines": (("item_code", "description"),),
}


def _names(spec: FieldSpec) -> tuple[str, ...]:
    return (key(spec.key), key(spec.label), *spec.aliases)


def header_score(kind: str) -> Callable[[Sequence[str]], int]:
    """FS-067 rule 1: how many of the kind's fields a row names, each counted once."""
    names = [set(_names(spec)) for spec in FIELDS[kind]]

    def score(cells: Sequence[str]) -> int:
        keys = {key(c) for c in cells if c}
        return sum(1 for n in names if n & keys)
    return score


# FS-067 rule 4a: a remembered rate column is the wrong state's prices on the next list
NEVER_REMEMBERED = frozenset({"rate"})


def suggest(kind: str, headers: list[str], remembered: dict[str, str] | None = None, *,
            empty: Collection[int] = ()) -> dict[str, int]:
    """Field to column, from the caller's last mapping of the same kind (by header
    text), then from the built-in names. A column is used once; a field once.

    A column in `empty` has no value on any row and is never suggested. A field
    whose best-named column is empty stays unsuggested rather than falling through
    to a weaker name: an empty "Rate" must not hand the rate to "MRP" (FS-067
    rule 4).

    A remembered column whose header is another field's own key or label is
    skipped when the file also has the remembered field's own column: a past
    "description on Item Code" must not take the template's Item code column when
    Description sits beside it (FS-068 rule 6). Without that column, as in the
    client's own file, the remembered match stands. Aliases do not count."""
    out: dict[str, int] = {}
    taken: set[int] = set(empty)
    by_key: dict[str, int] = {}
    for i, h in enumerate(headers):
        by_key.setdefault(key(h), i)
    known = {f.key for f in FIELDS[kind]} - NEVER_REMEMBERED
    own = {f.key: {key(f.key), key(f.label)} for f in FIELDS[kind]}
    for field_key, header in (remembered or {}).items():
        own_here = field_key in own and any(n in by_key for n in own[field_key])
        if own_here and any(key(header) in names for k, names in own.items() if k != field_key):
            continue
        col = by_key.get(key(header))
        if col is not None and col not in taken and field_key in known:
            out[field_key] = col
            taken.add(col)
    for spec in FIELDS[kind]:
        if spec.key in out:
            continue
        for alias in _names(spec):
            col = by_key.get(alias)
            if col is None:
                continue
            if col in empty:
                break
            if col not in taken:
                out[spec.key] = col
                taken.add(col)
                break
    return out


def mapping_problems(kind: str, mapping: dict[str, int], width: int) -> dict[str, str]:
    """Field paths to reasons. Empty when the mapping can be checked."""
    specs = {f.key: f for f in FIELDS[kind]}
    problems: dict[str, str] = {}
    seen: dict[int, str] = {}
    for field_key, column in mapping.items():
        if field_key not in specs:
            problems[f"mapping.{field_key}"] = "not a field of this import"
            continue
        if not 0 <= column < width:
            problems[f"mapping.{field_key}"] = f"no column {column}"
            continue
        if column in seen:
            problems[f"mapping.{field_key}"] = f"that column is already {seen[column]}"
            continue
        seen[column] = specs[field_key].label
    for spec in specs.values():
        if spec.required and spec.key not in mapping:
            problems.setdefault(f"mapping.{spec.key}", "required")
    for group in ONE_OF[kind]:
        if not any(k in mapping for k in group):
            problems.setdefault(f"mapping.{group[0]}", f"match {' or '.join(group)}")
    return problems
