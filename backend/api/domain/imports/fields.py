"""Each import kind's fields, the column guesses, and the mapping check (FS-062 section 4).

A mapping is `{field key: column index}`. The server only suggests one; the person
decides (rule 2).
"""

from __future__ import annotations

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


_PRODUCT = (
    FieldSpec("item_code", "Item code", False,
              "The product's item code. Give this or the description.",
              ("itemcode", "code", "sku", "productcode", "partno", "partnumber", "itemno")),
    FieldSpec("description", "Description", False,
              "The product's description, exactly as in the catalogue. Give this or the item "
              "code.", ("description", "product", "productname", "item", "itemname",
                        "itemdescription", "particulars", "name")),
)

FIELDS: dict[str, tuple[FieldSpec, ...]] = {
    "partners": (
        FieldSpec("partner_type", "Type", True,
                  "Distributor, dealer or sub-dealer.",
                  ("type", "partnertype", "category", "dealertype", "level")),
        FieldSpec("code", "Code", True, "Unique across all partners.",
                  ("code", "partnercode", "dealercode", "distributorcode", "id")),
        FieldSpec("name", "Name", True, "The partner's business name.",
                  ("name", "partnername", "dealername", "firmname", "businessname",
                   "distributorname", "firm", "shopname")),
        FieldSpec("state", "State", True, "A state's name or its two-letter code.",
                  ("state", "statename", "statecode")),
        FieldSpec("district", "District", False,
                  "A district in that state. Without one, the partner sits at the state.",
                  ("district", "dist", "districtname", "city")),
        FieldSpec("parent_code", "Parent code", False,
                  "The code of the partner one type up: a dealer's distributor, a sub-dealer's "
                  "dealer. It may be a row in this file.",
                  ("parentcode", "parent", "distributor", "distributorcode", "underdealer",
                   "dealer", "under")),
        FieldSpec("contact_name", "Contact name", False, "The person to speak to.",
                  ("contactname", "contact", "contactperson", "owner", "ownername",
                   "proprietor", "person")),
        FieldSpec("mobile", "Mobile", False, "An Indian mobile, in any common form.",
                  ("mobile", "mob", "mobileno", "mobilenumber", "phone", "phoneno", "contactno",
                   "contactnumber", "whatsapp", "cell")),
        FieldSpec("email", "Email", False, "", ("email", "emailid", "mail", "emailaddress")),
        FieldSpec("address", "Address", False, "", ("address", "fulladdress", "addr")),
        FieldSpec("gstin", "GSTIN", False, "15 characters.",
                  ("gstin", "gst", "gstno", "gstnumber", "gstinno")),
        FieldSpec("pan", "PAN", False, "10 characters.", ("pan", "panno", "pannumber")),
        FieldSpec("is_gst_registered", "GST registered", False,
                  "Yes or no. Without the column, yes when a GSTIN is given.",
                  ("gstregistered", "registered", "isgstregistered")),
        FieldSpec("credit_limit", "Credit limit", False, "Rupees, at most two decimals.",
                  ("creditlimit", "credit", "limit")),
        FieldSpec("payment_terms_days", "Payment terms (days)", False, "0 to 365.",
                  ("paymentterms", "paymenttermsdays", "creditdays", "terms", "days")),
    ),
    "price_list_items": (
        *_PRODUCT,
        FieldSpec("rate", "Rate", True,
                  "Rupees per unit, more than 0, at most two decimals. More is refused, not "
                  "rounded.", ("rate", "price", "unitprice", "amount", "mrp", "listprice",
                               "unitrate", "netrate")),
    ),
    "lines": (
        *_PRODUCT,
        FieldSpec("qty", "Quantity", True, "More than 0, in the product's unit.",
                  ("qty", "quantity", "qnty", "nos", "units")),
        FieldSpec("discount_pct", "Discount %", False, "0 to 100.",
                  ("discount", "discountpct", "disc", "discountpercent", "discount1")),
        FieldSpec("discount2_pct", "Discount 2 %", False, "0 to 100.",
                  ("discount2", "disc2", "discount2pct")),
        FieldSpec("discount3_pct", "Discount 3 %", False, "0 to 100.",
                  ("discount3", "disc3", "discount3pct")),
    ),
}

# At least one of each group must be mapped.
ONE_OF: dict[str, tuple[tuple[str, ...], ...]] = {
    "partners": (),
    "price_list_items": (("item_code", "description"),),
    "lines": (("item_code", "description"),),
}


def suggest(kind: str, headers: list[str],
            remembered: dict[str, str] | None = None) -> dict[str, int]:
    """Field to column, from the caller's last mapping of the same kind (by header
    text), then from the built-in names. A column is used once; a field once."""
    out: dict[str, int] = {}
    taken: set[int] = set()
    by_key: dict[str, int] = {}
    for i, h in enumerate(headers):
        by_key.setdefault(key(h), i)
    known = {f.key for f in FIELDS[kind]}
    for field_key, header in (remembered or {}).items():
        col = by_key.get(key(header))
        if col is not None and col not in taken and field_key in known:
            out[field_key] = col
            taken.add(col)
    for spec in FIELDS[kind]:
        if spec.key in out:
            continue
        for alias in (key(spec.key), key(spec.label), *spec.aliases):
            col = by_key.get(alias)
            if col is not None and col not in taken:
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
