"""Resolve the masters, run the engine, shape the answer (FS-010).

The only part of this feature that touches the database. It reads the product,
its classification, the tax rate for that classification and the price lists in
force, hands the domain plain dataclasses, and turns exact `Decimal`s into the
two-decimal strings the API returns.

Three decisions run through the whole module:

**Resolution is per product, not per document** (rule 3). A document-wide
resolution refuses a forty-line quotation because one product is missing a rate,
and it turns a state list into a wholesale replacement for the base rather than a
partial override. Per product, three state corrections over a complete base list
do what anyone would expect, and the response says when a document drew from more
than one list.

**Every line is resolved in one statement**, not one per line. A per-line query
takes a fresh snapshot each time, so a document could carry old rates on its
first hundred lines and new ones on its last hundred while a list was being
published underneath it.

**A master edit writes an audit row, not an `activity_event`** (rule 15). That is
a stated exemption from CLAUDE.md 4.1 rule 7, not an oversight: `activity_event`'s
read policy resolves by entity type and falls through to the system principal for
anything that is not a user, partner, lead or customer, so an event for a product
edit would be a row no administrator can read. Migration 010's `audit_row()`
trigger carries it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.money import round2
from api.domain.pricing.resolve import applicable, mixed_list_warning, pick
from api.domain.pricing.tax import (
    MAX_DOCUMENT_TOTAL,
    MAX_QTY,
    compute_line,
    document_totals,
)
from api.domain.pricing.types import (
    ZERO,
    DiscountStep,
    PricedDocument,
    PricedLine,
    PriceList,
    PricingError,
    Product,
    Rate,
    TaxRate,
    Tier,
)
from api.errors import ConflictError, NotFoundError, ValidationFailed
from api.schemas import products as sch
from api.services.clock import today_ist
from api.services.users import _pg_text, _sqlstate

# FS-042: how a document is taxed. Stored on it, never re-read from the setting.
TAX_TREATMENTS = ("domestic", "export_lut", "export_igst")

MAX_LINES = 200
MAX_FUTURE = dt.timedelta(days=365)
GST_SLABS = (Decimal("0"), Decimal("0.25"), Decimal("3"), Decimal("5"),
             Decimal("12"), Decimal("18"), Decimal("28"))


def _dec(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _s(v: Decimal) -> str:
    return f"{round2(v):.2f}"


def _opt(v: Any, places: int = 2) -> str | None:
    return None if v is None else f"{_dec(v):.{places}f}"


def _rate(v: Decimal) -> str:
    """A tax rate at three decimals, the precision `gst_rate.rate` carries.

    Not `_s`. Half of the 0.25 % slab is 0.125, and two decimals renders that as
    0.13 - so a line would print two halves summing to 0.26 against a slab of
    0.25. The domain keeps the halved rate exact for exactly this reason and the
    display layer was throwing it away again.
    """
    return f"{v:.3f}"


def _like(q: str) -> str:
    r"""A search term as a LIKE pattern. `%` and `_` are escaped, because a user
    typing an underscore means an underscore; the backslash is escaped first or
    escaping the others would be undone."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ── the caller's scope ───────────────────────────────────────────────────────

async def resolve_scope(db: AsyncSession, *, partner_id: str | None,
                        place_of_supply_territory_id: str) -> tuple[str | None, str, str]:
    """The tier to price at, and the state to tax against.

    **A partner's tier comes from their own row, never from the request** (rule 8).
    `partner_id` in a body is honoured only for a staff caller, and only inside
    their subtree, which the read policy decides. Otherwise a sub-dealer could ask
    for their parent's rates and get a confusing "no price" instead of a refusal.

    The place of supply is the **ship-to**, resolved up to its state through the
    territory closure, because for goods the place of supply is where delivery
    ends. Defaulting to the partner's own territory under-collects the inter-state
    tax, which is a credit note rather than a rounding argument.
    """
    caller_partner = (await db.execute(text("SELECT app_current_partner()"))).scalar_one_or_none()

    tier: str
    if caller_partner is not None:
        if partner_id is not None and str(partner_id) != str(caller_partner):
            raise ValidationFailed(
                fields={"partner_id": "A partner prices for itself; the tier comes from the "
                                      "signed-in account."})
        target = str(caller_partner)
        tier = (await db.execute(text(
            "SELECT price_tier::text FROM channel_partner WHERE id = CAST(:p AS uuid)"),
            {"p": target})).scalar_one()
    elif partner_id is not None:
        found = (await db.execute(text(
            "SELECT price_tier::text FROM channel_partner WHERE id = CAST(:p AS uuid)"),
            {"p": partner_id})).scalar_one_or_none()
        if found is None:
            # FS-020 rule 1: the dealer on a lead, quotation or order the caller can
            # see prices that document, though the dealer is outside their area.
            # Only the tier comes back, never the dealer's row.
            found = (await db.execute(text("SELECT document_partner_tier(CAST(:p AS uuid))"),
                                      {"p": partner_id})).scalar_one_or_none()
        if found is None:
            # A partner outside the caller's scope is invisible to the policy, so
            # this is both "does not exist" and "not yours" - one answer on
            # purpose, as everywhere else in this system.
            raise ValidationFailed(fields={"partner_id": "No such partner in your scope."})
        target, tier = str(partner_id), str(found)
    else:
        # No partner means a farmer, which is a tier migration 004 created and no
        # `channel_partner` row can hold. Without this the base list would be doing
        # two jobs: the fallback for every tier, and the retail price (GAP-091).
        target, tier = "", Tier.FARMER.value

    state = (await db.execute(text(
        "SELECT t.id::text FROM territory t "
        "JOIN territory_closure c ON c.ancestor_id = t.id "
        "WHERE c.descendant_id = CAST(:d AS uuid) AND t.level = 'state'"),
        {"d": place_of_supply_territory_id})).scalar_one_or_none()
    if state is None:
        raise ValidationFailed(fields={
            "place_of_supply_territory_id": "This territory does not sit under a state."})
    return (target or None), tier, state


async def seller_state(db: AsyncSession, *, gstin_id: str | None,
                       as_of: dt.date) -> tuple[str, str, str]:
    """The registration in force, the state it is registered in, and that state's code.

    `Schema-Corrections.md` 1.3 resolves this from the supplying warehouse, which
    does not exist yet, so the default registration is the interim rule (GAP-088).
    The request already accepts an explicit id, so a second registration is
    additive rather than a breaking change.
    """
    row = (await db.execute(text(
        "SELECT g.id::text, t.id::text, t.code::text FROM seller_gstin g "
        "JOIN territory t ON t.id = g.state_territory_id "
        "WHERE (CAST(:g AS uuid) IS NULL OR g.id = CAST(:g AS uuid)) "
        "AND (CAST(:g AS uuid) IS NOT NULL OR g.is_default) "
        "AND g.is_active AND g.deleted_at IS NULL "
        "AND daterange(g.effective_from, g.effective_to, '[)') @> CAST(:d AS date)"),
        {"g": gstin_id, "d": as_of})).one_or_none()
    if row is None:
        raise NotFoundError(f"No seller registration is in force on {as_of}.")
    return str(row[0]), str(row[1]), row[2] or ""


# ── the masters, in one statement each ───────────────────────────────────────

async def load_products(db: AsyncSession, product_ids: Sequence[str],
                        as_of: dt.date) -> dict[str, tuple[Product, TaxRate]]:
    rows = (await db.execute(text(
        "SELECT p.id::text, p.description::text, u.code::text, u.decimals, p.pack_multiple, "
        "       p.is_active, p.provisional_fields, "
        "       h.hsn_code, g.id::text, g.rate "
        "FROM product p "
        "JOIN uom u ON u.id = p.uom_id "
        "LEFT JOIN product_hsn h ON h.product_id = p.id AND h.deleted_at IS NULL "
        "     AND daterange(h.effective_from, h.effective_to, '[)') @> CAST(:d AS date) "
        "LEFT JOIN gst_rate g ON g.hsn_code = h.hsn_code AND g.deleted_at IS NULL "
        "     AND daterange(g.effective_from, g.effective_to, '[)') @> CAST(:d AS date) "
        "WHERE p.id = ANY(CAST(:ids AS uuid[])) AND p.deleted_at IS NULL"),
        {"ids": list(product_ids), "d": as_of})).all()

    out: dict[str, tuple[Product, TaxRate]] = {}
    for r in rows:
        provisional = frozenset(r[6] or [])
        product = Product(id=r[0], description=r[1], uom_code=r[2], uom_decimals=r[3],
                          pack_multiple=_dec(r[4]) if r[4] is not None else None,
                          is_active=r[5], provisional_fields=provisional)
        tax = TaxRate(gst_rate_id=r[8] or "", hsn_code=r[7] or "",
                      slab=_dec(r[9]) if r[9] is not None else Decimal(-1),
                      is_provisional="gst_slab" in provisional or "hsn_code" in provisional)
        out[r[0]] = (product, tax)
    return out


async def load_rates(db: AsyncSession, product_ids: Sequence[str], *, as_of: dt.date,
                     state_territory_id: str, tier: str) -> dict[str, list[Rate]]:
    """Every rate every applicable published list holds for these products, in one
    statement, so the whole document reads one snapshot."""
    rows = (await db.execute(text(
        "SELECT i.product_id::text, i.id::text, i.rate, "
        "       l.id::text, l.name, l.state_territory_id::text, l.channel_tier::text, "
        "       l.effective_from, l.effective_to, l.is_provisional "
        "FROM price_list_item i JOIN price_list l ON l.id = i.price_list_id "
        "WHERE i.product_id = ANY(CAST(:ids AS uuid[])) "
        "AND l.status = 'published' AND l.deleted_at IS NULL "
        "AND daterange(l.effective_from, l.effective_to, '[)') @> CAST(:d AS date) "
        "AND (l.state_territory_id IS NULL OR l.state_territory_id = CAST(:s AS uuid)) "
        "AND (l.channel_tier IS NULL OR l.channel_tier = CAST(:t AS channel_tier))"),
        {"ids": list(product_ids), "d": as_of, "s": state_territory_id, "t": tier})).all()

    lists: dict[str, PriceList] = {}
    out: dict[str, list[Rate]] = {}
    for r in rows:
        if r[3] not in lists:
            lists[r[3]] = PriceList(id=r[3], name=r[4], state_territory_id=r[5],
                                    channel_tier=Tier(r[6]) if r[6] else None,
                                    effective_from=r[7], effective_to=r[8], is_provisional=r[9])
        out.setdefault(r[0], []).append(Rate(price_list_item_id=r[1], price_list=lists[r[3]],
                                             rate=_dec(r[2])))
    # The scope filter above and this one say the same thing twice, on purpose: the
    # query narrows what is read, and the domain decides what may be priced from.
    for rates in out.values():
        allowed = {pl.id for pl in applicable([r.price_list for r in rates],
                                              state_territory_id=state_territory_id, tier=tier)}
        rates[:] = [r for r in rates if r.price_list.id in allowed]
    return out


# ── the pricing preview ──────────────────────────────────────────────────────

def _check_quantity(product: Product, qty: Decimal, index: int) -> None:
    field = f"lines[{index}].qty"
    # Out-of-range quantities are the domain's refusal, with the domain's message.
    # Checking them here as well would duplicate it, and quantizing one first
    # would raise `InvalidOperation` on a quantity large enough to exceed the
    # decimal context.
    if not ZERO < qty <= MAX_QTY:
        return
    if qty != qty.quantize(Decimal(1).scaleb(-product.uom_decimals)):
        raise ValidationFailed(fields={field: (
            f"{product.uom_code} takes {product.uom_decimals} decimal places; "
            f"{qty:f} has more.")})
    if product.pack_multiple is not None and qty % product.pack_multiple != 0:
        raise ValidationFailed(fields={field: (
            f"This product is sold in multiples of {product.pack_multiple:f} "
            f"{product.uom_code}.")})


@dataclass(frozen=True)
class LineSpec:
    """One line to price: what the preview posts and what a saved line re-resolves.
    `discounts` is the cascade, tier one first."""

    product_id: str
    qty: Decimal
    discounts: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class PricedContext:
    """A priced document and the resolution around it: the date, the registration
    and the state it supplies from, the ship-to state and its code, the tier. What
    the preview returns and what the quotation stores (FS-005 5.3)."""

    document: PricedDocument
    as_of: dt.date
    seller_gstin_id: str
    seller_state_id: str
    seller_code: str
    place_of_supply_state_id: str
    place_of_supply_code: str
    intra_state: bool
    tier: str
    partner_id: str | None


async def price_document(db: AsyncSession, *, partner_id: str | None,
                         place_of_supply_territory_id: str, seller_gstin_id: str | None,
                         as_of: dt.date | None, lines: Sequence[LineSpec],
                         existing: bool = False,
                         tax_as_of: dt.date | None = None,
                         tax_treatment: str = "domestic") -> PricedContext:
    """Resolve and price a set of lines against the masters in force on a date.
    Stores nothing and locks nothing (rule 14).

    **One implementation for the preview and the save.** `POST /pricing/quote-lines`
    and every quotation write call this, so the figures a screen previews and the
    figures a document stores cannot disagree, which is what the `rate_changed`
    comparison rests on (FS-005 rule 4).

    `existing=True` is a document re-resolving lines it already holds: a product
    discontinued since the line was saved is priced with a warning rather than
    refused, and the quantity is not re-validated against a unit or pack multiple
    that may have changed since it was typed (FS-005 rule 5, edge cases 8 and 13).
    A new line is refused on both, as before.

    `tax_as_of` separates the tax from the price (FS-011 rule 3): rates resolve at
    `as_of`, the HSN, the GST slab and the seller registration at `tax_as_of`,
    because tax is charged on the date of supply. It defaults to `as_of`, which is
    what a quotation and the preview do.

    `tax_treatment` is the document's stored treatment, never the setting
    (FS-042 rule 5). An export is never intra-state, whatever the stored place of
    supply says (IGST Act s.7(5)(a)); under a LUT each line is priced at slab 0
    but keeps its product's slab and rate id, so the figures can be rebuilt if
    the client turns out to pay IGST and claim a refund (rule 2a).
    """
    if tax_treatment not in TAX_TREATMENTS:
        raise ValidationFailed(fields={"tax_treatment": f"One of {', '.join(TAX_TREATMENTS)}."})
    day = as_of or today_ist()
    tax_day = tax_as_of or day
    if day > today_ist() + MAX_FUTURE:
        raise ValidationFailed(fields={"as_of": "A price date may not be more than a year ahead."})
    if len(lines) > MAX_LINES:
        raise ValidationFailed(fields={"lines": f"At most {MAX_LINES} lines."})

    target, tier, pos_state = await resolve_scope(
        db, partner_id=partner_id, place_of_supply_territory_id=place_of_supply_territory_id)
    gstin_id, seller, seller_code = await seller_state(db, gstin_id=seller_gstin_id,
                                                       as_of=tax_day)
    intra_state = seller == pos_state and tax_treatment == "domestic"
    pos_code = (await db.execute(
        text("SELECT code::text FROM territory WHERE id = CAST(:t AS uuid)"),
        {"t": pos_state})).scalar_one_or_none() or ""

    ids = [ln.product_id for ln in lines]
    products = await load_products(db, ids, tax_day)
    rates = await load_rates(db, ids, as_of=day, state_territory_id=pos_state, tier=tier)

    missing = {f"lines[{i}].product_id": "No such product."
               for i, ln in enumerate(lines) if ln.product_id not in products}
    if missing:
        raise ValidationFailed(fields=missing)

    # Three refusals, each reported for every line it applies to rather than the
    # first: fixing a forty-line quotation one line per round trip is forty round
    # trips.
    inactive: dict[str, str] = {}
    untaxed: dict[str, str] = {}
    unpriced: dict[str, str] = {}
    chosen: dict[str, Rate] = {}
    discontinued = 0
    for i, ln in enumerate(lines):
        product, tax = products[ln.product_id]
        if not product.is_active:
            if existing:
                discontinued += 1
            else:
                inactive[f"lines[{i}].product_id"] = f"{product.description} is no longer sold."
        if tax.slab < 0:
            untaxed[f"lines[{i}].product_id"] = (
                f"{product.description} has no tax rate in force on {tax_day}.")
        winner = pick(rates.get(ln.product_id, []))
        if winner is None:
            remedy = (" Revise the document at a date a list covers, or remove the line."
                      if existing else "")
            unpriced[f"lines[{i}].product_id"] = (
                f"{product.description} has no price in force on {day}.{remedy}")
        else:
            chosen[str(i)] = winner
    if inactive:
        raise ValidationFailed(code="product_inactive", fields=inactive)
    if untaxed:
        raise ValidationFailed(code="product_missing_tax_rate", fields=untaxed)
    if unpriced:
        raise ValidationFailed(code="product_not_priced", fields=unpriced)

    priced: list[PricedLine] = []
    for i, ln in enumerate(lines):
        product, tax = products[ln.product_id]
        if not existing:
            _check_quantity(product, ln.qty, i)
        rate = chosen[str(i)]
        tiers = tuple(ln.discounts) or (ZERO,)
        try:
            money = compute_line(rate=rate.rate, qty=ln.qty, discounts=tiers,
                                 slab=ZERO if tax_treatment == "export_lut" else tax.slab,
                                 intra_state=intra_state)
        except PricingError as exc:
            raise ValidationFailed(
                exc.message, code=exc.code,
                fields={f"lines[{i}].{exc.field_path or 'qty'}": exc.message}) from exc
        priced.append(PricedLine(product=product, qty=ln.qty, discount_pct=tiers[0],
                                 rate=rate, tax=tax, money=money, discounts=tiers))

    try:
        totals = document_totals(tuple(p.money for p in priced))
    except PricingError as exc:
        raise ValidationFailed(exc.message, code=exc.code, fields={"lines": exc.message}) from exc

    warnings: list[str] = []
    if day > today_ist():
        warnings.append(f"future_price_date: {day} is ahead of today, so these are the rates "
                        f"that will be in force then, not today's.")
    mixed = mixed_list_warning(chosen)
    if mixed:
        warnings.append(mixed)
    provisional = sum(1 for p in priced if p.provisional_fields)
    if provisional:
        warnings.append(f"provisional_pricing: {provisional} of {len(priced)} lines use a "
                        f"stand-in rate or tax slab that the client has not confirmed. Fine "
                        f"for testing, not for a quotation anyone sends.")
    if discontinued:
        warnings.append(f"discontinued_products: {discontinued} of {len(priced)} lines are "
                        f"products no longer sold. They stay priced on this document; they "
                        f"cannot be added to a new one.")

    document = PricedDocument(lines=tuple(priced), totals=totals, intra_state=intra_state,
                              warnings=tuple(warnings))
    return PricedContext(document=document, as_of=day, seller_gstin_id=gstin_id,
                         seller_state_id=seller, seller_code=seller_code,
                         place_of_supply_state_id=pos_state, place_of_supply_code=pos_code,
                         intra_state=intra_state, tier=tier, partner_id=target)


async def quote_lines(db: AsyncSession, body: sch.QuoteLinesRequest) -> sch.QuoteLinesResponse:
    """Price and tax a set of lines. Stores nothing and locks nothing (rule 14)."""
    ctx = await price_document(
        db, partner_id=body.partner_id,
        place_of_supply_territory_id=body.place_of_supply_territory_id,
        seller_gstin_id=body.seller_gstin_id, as_of=body.as_of,
        lines=[LineSpec(product_id=ln.product_id, qty=ln.qty, discounts=ln.discounts)
               for ln in body.lines],
        tax_treatment=body.tax_treatment)
    return _quote_response(ctx.document, as_of=ctx.as_of, gstin_id=ctx.seller_gstin_id,
                           seller_code=ctx.seller_code, pos_code=ctx.place_of_supply_code)


def _cascade(steps: tuple[DiscountStep, ...]) -> dict[str, str]:
    """The three tiers as the sheet prints them, always three, zero-filled: the
    columns exist whatever the percentages were (FS-005 rule 6)."""
    padded = list(steps) + [DiscountStep(pct=ZERO, amount=ZERO, after=steps[-1].after)] * (
        3 - len(steps))
    s1, s2, s3 = padded[:3]
    return {
        "discount_pct": f"{s1.pct:.3f}", "discount1_amt": _s(s1.amount),
        "after_discount1": _s(s1.after),
        "discount2_pct": f"{s2.pct:.3f}", "discount2_amt": _s(s2.amount),
        "after_discount2": _s(s2.after),
        "discount3_pct": f"{s3.pct:.3f}", "discount3_amt": _s(s3.amount),
    }


def _quote_response(doc: PricedDocument, *, as_of: dt.date, gstin_id: str, seller_code: str,
                    pos_code: str) -> sch.QuoteLinesResponse:
    lines = [
        sch.QuoteLine(
            product_id=p.product.id, description=p.product.description, uom=p.product.uom_code,
            qty=f"{p.qty:.{p.product.uom_decimals}f}", rate=_s(p.rate.rate),
            price_list_id=p.rate.price_list.id, price_list_item_id=p.rate.price_list_item_id,
            gross=_s(p.money.gross), **_cascade(p.money.steps),
            discount=_s(p.money.discount), taxable=_s(p.money.taxable),
            hsn_code=p.tax.hsn_code, gst_slab=_rate(p.tax.slab), gst_rate_id=p.tax.gst_rate_id,
            cgst_rate=_rate(p.money.cgst_rate), sgst_rate=_rate(p.money.sgst_rate),
            igst_rate=_rate(p.money.igst_rate),
            cgst=_s(p.money.cgst), sgst=_s(p.money.sgst), igst=_s(p.money.igst),
            total=_s(p.money.total), provisional_fields=list(p.provisional_fields))
        for p in doc.lines
    ]
    t = doc.totals
    return sch.QuoteLinesResponse(
        as_of=as_of, seller_gstin_id=gstin_id, seller_state=seller_code,
        place_of_supply_state=pos_code, intra_state=doc.intra_state,
        price_list_ids=sorted({p.rate.price_list.id for p in doc.lines}),
        lines=lines,
        totals=sch.QuoteTotals(gross=_s(t.gross), discount=_s(t.discount), taxable=_s(t.taxable),
                               cgst=_s(t.cgst), sgst=_s(t.sgst), igst=_s(t.igst),
                               total=_s(t.total)),
        warnings=list(doc.warnings))


# ── the catalogue ────────────────────────────────────────────────────────────

_PRODUCT_SELECT = """
SELECT p.id::text AS id, p.item_code::text AS item_code, p.description::text AS description,
       c.code::text AS category, p.quotation_category::text AS quotation_category,
       u.code::text AS uom, u.decimals AS uom_decimals,
       h.hsn_code AS hsn_code, g.rate AS gst_slab,
       p.mrp AS mrp, p.pack_multiple AS pack_multiple,
       p.is_subsidy_eligible AS is_subsidy_eligible, p.is_active AS is_active,
       p.provisional_fields AS provisional_fields
FROM product p
JOIN product_category c ON c.id = p.product_category_id
JOIN uom u ON u.id = p.uom_id
-- No `is_active` on either join, matching `load_products`. The picker has to show
-- the classification and slab that pricing will actually use; reading the flag in
-- one and not the other is how a screen and an invoice come to disagree.
LEFT JOIN product_hsn h ON h.product_id = p.id AND h.deleted_at IS NULL
     AND daterange(h.effective_from, h.effective_to, '[)') @> CAST(:d AS date)
LEFT JOIN gst_rate g ON g.hsn_code = h.hsn_code AND g.deleted_at IS NULL
     AND daterange(g.effective_from, g.effective_to, '[)') @> CAST(:d AS date)
"""


def _product(r: Any) -> sch.Product:
    return sch.Product(
        id=r.id, item_code=r.item_code, description=r.description, product_category=r.category,
        quotation_category=r.quotation_category, uom=r.uom, uom_decimals=r.uom_decimals,
        hsn_code=r.hsn_code, gst_slab=_opt(r.gst_slab, 3), mrp=_opt(r.mrp),
        pack_multiple=_opt(r.pack_multiple, 3), is_subsidy_eligible=r.is_subsidy_eligible,
        is_active=r.is_active, provisional_fields=list(r.provisional_fields or []))


async def list_products(db: AsyncSession, *, q: str | None, category: str | None,
                        quotation_category: str | None, active: bool | None,
                        as_of: dt.date | None, page: int, limit: int) -> sch.ProductPage:
    """The picker, and the catalogue screen behind it.

    Offset-paged with a total, unlike the lead list: this table is a fixed 1,092
    rows that every signed-in user sees in full, so the count is cheap and a
    picker wants to show it. `count(*) OVER ()` takes it from the same statement,
    so the total and the rows on the page always agree.
    """
    day = as_of or today_ist()
    params: dict[str, Any] = {"d": day, "limit": limit, "offset": (page - 1) * limit,
                              "q": _like(q) if q else None, "cat": category,
                              "qc": quotation_category, "active": active}
    rows = (await db.execute(text(_PRODUCT_SELECT.replace(
        "SELECT p.id::text AS id",
        "SELECT count(*) OVER () AS total, p.id::text AS id", 1) + r"""
WHERE p.deleted_at IS NULL
  AND (CAST(:q AS text) IS NULL OR p.description::text ILIKE CAST(:q AS text) ESCAPE '\')
  AND (CAST(:cat AS text) IS NULL OR c.code = CAST(:cat AS citext))
  AND (CAST(:qc AS text) IS NULL OR p.quotation_category = CAST(:qc AS quotation_category))
  AND (CAST(:active AS boolean) IS NULL OR p.is_active = CAST(:active AS boolean))
ORDER BY p.description, p.id
LIMIT :limit OFFSET :offset"""), params)).all()
    total = int(rows[0].total) if rows else 0
    return sch.ProductPage(data=[_product(r) for r in rows],
                           meta=sch.OffsetMeta(page=page, limit=limit, total=total))


async def get_product(db: AsyncSession, product_id: str,
                      as_of: dt.date | None = None) -> sch.Product:
    row = (await db.execute(text(
        _PRODUCT_SELECT + " WHERE p.id = CAST(:id AS uuid) AND p.deleted_at IS NULL"),
        {"id": product_id, "d": as_of or today_ist()})).one_or_none()
    if row is None:
        raise NotFoundError("No such product.")
    return _product(row)


async def _lookup(db: AsyncSession, table: str, code: str, field: str) -> str:
    found = (await db.execute(text(
        f"SELECT id::text FROM {table} WHERE code = CAST(:c AS citext) AND deleted_at IS NULL"),
        {"c": code})).scalar_one_or_none()
    if found is None:
        # Never created implicitly: a typo in a category code would otherwise
        # become a new category, and the picker would grow a group of one.
        raise ValidationFailed(
            fields={field: f"{code!r} is not a known {field.replace('_', ' ')}."})
    return str(found)


def _duplicate(exc: DBAPIError) -> ConflictError | None:
    if _sqlstate(exc) != "23505":
        return None
    msg = _pg_text(exc)
    if "uq_product_description" in msg:
        return ConflictError("A product with this description already exists. Edit that one "
                             "rather than adding a second.", code="duplicate_description",
                             fields={"description": "already in use"})
    if "uq_product_item_code" in msg:
        return ConflictError("A product with this item code already exists.",
                             code="duplicate_item_code", fields={"item_code": "already in use"})
    return None


async def create_product(db: AsyncSession, body: sch.ProductCreate) -> sch.Product:
    """Add a catalogue row. Nothing here is provisional: a value an administrator
    typed is the client's own, which is what `provisional_fields` marks the
    absence of."""
    category_id = await _lookup(db, "product_category", body.product_category, "product_category")
    uom_id = await _lookup(db, "uom", body.uom, "uom")
    try:
        new_id: Any = (await db.execute(text(
            "INSERT INTO product (description, item_code, product_category_id, "
            "  quotation_category, uom_id, mrp, pack_multiple, is_subsidy_eligible, created_by) "
            "VALUES (CAST(:desc AS citext), CAST(:code AS citext), CAST(:cat AS uuid), "
            "  CAST(:qc AS quotation_category), CAST(:uom AS uuid), :mrp, :pack, :elig, "
            "  app_current_user_id()) RETURNING id::text"),
            {"desc": body.description, "code": body.item_code, "cat": category_id,
             "qc": body.quotation_category, "uom": uom_id, "mrp": body.mrp,
             "pack": body.pack_multiple, "elig": body.is_subsidy_eligible})).scalar_one()
    except DBAPIError as exc:
        conflict = _duplicate(exc)
        if conflict:
            raise conflict from exc
        raise
    return await get_product(db, str(new_id))


# Which `provisional_fields` entry each editable column owns. A PATCH that sets a
# column clears its own entry and no other: rev 1 had one boolean over all four,
# so setting a pack multiple would have marked a guessed tax slab as confirmed.
_CLEARS = {"mrp": "mrp", "pack_multiple": "pack_multiple"}

_PATCH_COLUMNS = (
    ("description", "description = CAST(:description AS citext)"),
    ("item_code", "item_code = CAST(:item_code AS citext)"),
    ("quotation_category",
     "quotation_category = CAST(:quotation_category AS quotation_category)"),
    ("mrp", "mrp = :mrp"),
    ("pack_multiple", "pack_multiple = :pack_multiple"),
    ("is_subsidy_eligible", "is_subsidy_eligible = :is_subsidy_eligible"),
    ("is_active", "is_active = :is_active"),
)


async def patch_product(db: AsyncSession, product_id: str, body: sch.ProductPatch) -> sch.Product:
    sent = body.model_dump(exclude_unset=True)
    if not sent:
        return await get_product(db, product_id)

    sets: list[str] = []
    params: dict[str, Any] = {"id": product_id}
    if "product_category" in sent:
        params["cat"] = await _lookup(db, "product_category", body.product_category or "",
                                      "product_category")
        sets.append("product_category_id = CAST(:cat AS uuid)")
    if "uom" in sent:
        params["uom"] = await _lookup(db, "uom", body.uom or "", "uom")
        sets.append("uom_id = CAST(:uom AS uuid)")
    for name, expr in _PATCH_COLUMNS:
        if name in sent:
            params[name] = sent[name]
            sets.append(expr)
    cleared = [_CLEARS[name] for name in sent if name in _CLEARS]
    if cleared:
        params["cleared"] = cleared
        sets.append("provisional_fields = ARRAY(SELECT unnest(provisional_fields) "
                    "EXCEPT SELECT unnest(CAST(:cleared AS text[])))")
    sets.append("updated_by = app_current_user_id()")

    try:
        touched = (await db.execute(text(
            f"UPDATE product SET {', '.join(sets)} "
            "WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL RETURNING id"),
            params)).scalar_one_or_none()
    except DBAPIError as exc:
        conflict = _duplicate(exc)
        if conflict:
            raise conflict from exc
        raise
    if touched is None:
        raise NotFoundError("No such product.")
    return await get_product(db, product_id)


# ── classification, and the Council's slab ───────────────────────────────────

async def _close_predecessor(db: AsyncSession, *, table: str, key_column: str, key: Any,
                             cast: str, effective_from: dt.date, code: str) -> dt.date | None:
    """Close the dated row in force at the new row's start date, and say where the
    new row has to stop.

    Two things, because a dated insert needs both ends.

    **The predecessor is closed at the new row's start**, and a new row starting on
    the same day as the one in force is refused rather than silently replacing it:
    closing a row at its own start date leaves an empty range, which is in force
    for no day at all, and every past document that cited that row can no longer
    explain itself.

    **The successor bounds the new row.** Inserting open-ended when a later
    revision already exists overlaps it, and the caller gets a raw exclusion
    violation as a 500 instead of the row they asked for - even though the gap
    between the two is a perfectly good window. The loader had this exact shape
    and a cross-vendor review found it there; the same shape was here, in the two
    endpoints that write a dated fact.
    """
    current = (await db.execute(text(
        f"SELECT id::text AS id, effective_from FROM {table} "
        f"WHERE {key_column} = CAST(:k AS {cast}) AND deleted_at IS NULL "
        # `effective_from <= :d` is not decoration. Without it an open-ended row
        # that STARTS LATER satisfies the other half, gets picked as the row in
        # force, and the same-day guard below then refuses a write whose date is
        # months earlier - naming a conflict with a row that had not begun.
        "AND effective_from <= CAST(:d AS date) "
        "AND (effective_to IS NULL OR effective_to > CAST(:d AS date)) "
        "ORDER BY effective_from DESC LIMIT 1"),
        {"k": key, "d": effective_from})).one_or_none()
    if current is not None:
        if current.effective_from >= effective_from:
            raise ConflictError(
                f"A row already starts on {current.effective_from}. Pick a later date, or correct "
                f"that row instead of adding a second one for the same day.",
                code=code, fields={"effective_from": f"not later than {current.effective_from}"})
        await db.execute(text(
            f"UPDATE {table} SET effective_to = CAST(:d AS date), "
            "updated_by = app_current_user_id() WHERE id = CAST(:id AS uuid)"),
            {"d": effective_from, "id": current.id})

    return (await db.execute(text(
        f"SELECT min(effective_from) FROM {table} "
        f"WHERE {key_column} = CAST(:k AS {cast}) AND deleted_at IS NULL "
        "AND effective_from > CAST(:d AS date)"),
        {"k": key, "d": effective_from})).scalar_one_or_none()


async def assign_hsn(db: AsyncSession, product_id: str, body: sch.HsnAssign) -> list[sch.HsnRow]:
    """Classify a product from a date, closing the classification in force.

    Its own endpoint because it is its own dated fact: a tariff heading changes
    for tariff reasons, not because anything about the product did.
    """
    exists = (await db.execute(text(
        "SELECT id FROM product WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": product_id})).scalar_one_or_none()
    if exists is None:
        raise NotFoundError("No such product.")

    until = await _close_predecessor(
        db, table="product_hsn", key_column="product_id", key=product_id, cast="uuid",
        effective_from=body.effective_from, code="hsn_same_start_date")
    await db.execute(text(
        "INSERT INTO product_hsn (product_id, hsn_code, effective_from, effective_to, created_by) "
        "VALUES (CAST(:p AS uuid), :h, CAST(:d AS date), CAST(:u AS date), "
        "        app_current_user_id())"),
        {"p": product_id, "h": body.hsn_code, "d": body.effective_from, "u": until})

    # The classification is now the client's, so it is no longer a stand-in. The
    # slab follows only if a rate exists for the new code on that date; otherwise
    # the product would claim a confirmed slab it has no row for.
    rated = (await db.execute(text(
        "SELECT 1 FROM gst_rate WHERE hsn_code = :h AND is_active AND deleted_at IS NULL "
        "AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date)"),
        {"h": body.hsn_code, "d": body.effective_from})).scalar_one_or_none()
    clears = ["hsn_code"] + (["gst_slab"] if rated else [])
    await db.execute(text(
        "UPDATE product SET provisional_fields = "
        "  ARRAY(SELECT unnest(provisional_fields) EXCEPT SELECT unnest(CAST(:c AS text[]))), "
        "  updated_by = app_current_user_id() WHERE id = CAST(:id AS uuid)"),
        {"c": clears, "id": product_id})
    return await hsn_history(db, product_id)


async def hsn_history(db: AsyncSession, product_id: str) -> list[sch.HsnRow]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, hsn_code, effective_from, effective_to FROM product_hsn "
        "WHERE product_id = CAST(:p AS uuid) AND deleted_at IS NULL "
        "ORDER BY effective_from DESC"), {"p": product_id})).all()
    return [sch.HsnRow(id=r.id, hsn_code=r.hsn_code, effective_from=r.effective_from,
                       effective_to=r.effective_to) for r in rows]


async def list_tax_rates(db: AsyncSession, *, hsn_code: str | None, in_force: bool,
                         page: int, limit: int) -> sch.TaxRatePage:
    params: dict[str, Any] = {"h": hsn_code, "d": today_ist(), "force": in_force,
                              "limit": limit, "offset": (page - 1) * limit}
    rows = (await db.execute(text(
        "SELECT count(*) OVER () AS total, id::text AS id, hsn_code, rate, "
        "       effective_from, effective_to, is_active "
        "FROM gst_rate WHERE deleted_at IS NULL "
        "AND (CAST(:h AS text) IS NULL OR hsn_code = CAST(:h AS text)) "
        "AND (NOT CAST(:force AS boolean) "
        "     OR daterange(effective_from, effective_to, '[)') @> CAST(:d AS date)) "
        "ORDER BY hsn_code, effective_from DESC LIMIT :limit OFFSET :offset"), params)).all()
    total = int(rows[0].total) if rows else 0
    return sch.TaxRatePage(
        data=[sch.TaxRate(id=r.id, hsn_code=r.hsn_code, rate=f"{_dec(r.rate):.3f}",
                          effective_from=r.effective_from, effective_to=r.effective_to,
                          is_active=r.is_active) for r in rows],
        meta=sch.OffsetMeta(page=page, limit=limit, total=total))


async def set_tax_rate(db: AsyncSession, hsn_code: str,
                       body: sch.TaxRateUpsert) -> sch.TaxRatePage:
    """The Council's rate for a code, from a date. One row per change, not one per
    product: a slab change is a legal event affecting every product on that code."""
    if body.rate not in GST_SLABS:
        raise ValidationFailed(fields={"rate": (
            "Not a slab in force. Use one of "
            + ", ".join(f"{s.normalize():f}" for s in GST_SLABS) + ".")})
    until = await _close_predecessor(
        db, table="gst_rate", key_column="hsn_code", key=hsn_code, cast="text",
        effective_from=body.effective_from, code="tax_rate_same_start_date")
    await db.execute(text(
        "INSERT INTO gst_rate (hsn_code, rate, effective_from, effective_to, created_by) "
        "VALUES (:h, :r, CAST(:d AS date), CAST(:u AS date), app_current_user_id())"),
        {"h": hsn_code, "r": body.rate, "d": body.effective_from, "u": until})

    # Every product classified under this code on that date now has a confirmed
    # slab, whatever it had before.
    await db.execute(text(
        "UPDATE product SET provisional_fields = "
        "  ARRAY(SELECT unnest(provisional_fields) EXCEPT SELECT 'gst_slab'), "
        "  updated_by = app_current_user_id() "
        "WHERE 'gst_slab' = ANY(provisional_fields) AND deleted_at IS NULL AND EXISTS ("
        "  SELECT 1 FROM product_hsn h WHERE h.product_id = product.id AND h.hsn_code = :h "
        "  AND h.is_active AND h.deleted_at IS NULL "
        "  AND daterange(h.effective_from, h.effective_to, '[)') @> CAST(:d AS date))"),
        {"h": hsn_code, "d": body.effective_from})
    return await list_tax_rates(db, hsn_code=hsn_code, in_force=False, page=1, limit=50)


# ── price lists ──────────────────────────────────────────────────────────────

_LIST_SELECT = """
SELECT l.id::text AS id, l.name AS name, l.status::text AS status,
       l.published_at AS published_at, l.effective_from AS effective_from,
       l.effective_to AS effective_to, l.is_active AS is_active,
       l.is_provisional AS is_provisional, l.channel_tier::text AS channel_tier,
       t.id::text AS state_id, t.name AS state_name, t.code::text AS state_code,
       (SELECT count(*) FROM price_list_item i WHERE i.price_list_id = l.id) AS item_count,
       (SELECT count(*) FROM product p WHERE p.is_active AND p.deleted_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM price_list_item i
                          WHERE i.price_list_id = l.id AND i.product_id = p.id)) AS unpriced_count
FROM price_list l
LEFT JOIN territory t ON t.id = l.state_territory_id
"""


def _price_list(r: Any) -> sch.PriceList:
    return sch.PriceList(
        id=r.id, name=r.name,
        state_territory=(sch.StateRef(id=r.state_id, name=r.state_name, code=r.state_code)
                         if r.state_id else None),
        channel_tier=r.channel_tier, status=r.status,
        published_at=r.published_at.isoformat() if r.published_at else None,
        effective_from=r.effective_from, effective_to=r.effective_to,
        is_active=r.is_active, is_provisional=r.is_provisional,
        item_count=int(r.item_count), unpriced_count=int(r.unpriced_count))


async def list_price_lists(db: AsyncSession, *, status: str | None, state_territory_id: str | None,
                           channel_tier: str | None, page: int, limit: int) -> sch.PriceListPage:
    """What a partner sees here is already narrowed by the restrictive tier policy
    in migration 010. Nothing is filtered a second time in Python."""
    params: dict[str, Any] = {"st": status, "state": state_territory_id, "tier": channel_tier,
                              "limit": limit, "offset": (page - 1) * limit}
    rows = (await db.execute(text(_LIST_SELECT.replace(
        "SELECT l.id::text AS id", "SELECT count(*) OVER () AS total, l.id::text AS id", 1) + """
WHERE l.deleted_at IS NULL
  AND (CAST(:st AS text) IS NULL OR l.status = CAST(:st AS price_list_status))
  AND (CAST(:state AS text) IS NULL OR l.state_territory_id = CAST(:state AS uuid))
  AND (CAST(:tier AS text) IS NULL OR l.channel_tier = CAST(:tier AS channel_tier))
ORDER BY l.effective_from DESC, l.name, l.id
LIMIT :limit OFFSET :offset"""), params)).all()
    total = int(rows[0].total) if rows else 0
    return sch.PriceListPage(data=[_price_list(r) for r in rows],
                             meta=sch.OffsetMeta(page=page, limit=limit, total=total))


async def get_price_list(db: AsyncSession, list_id: str) -> sch.PriceList:
    row = (await db.execute(text(
        _LIST_SELECT + " WHERE l.id = CAST(:id AS uuid) AND l.deleted_at IS NULL"),
        {"id": list_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such price list.")
    return _price_list(row)


async def _raw_list(db: AsyncSession, list_id: str, *, for_update: bool = False) -> Any:
    """The list's own row. `for_update` on every path that decides from its status.

    FS-010 section 5 and migration 010's docstring both said this read took
    `FOR UPDATE`, and it did not. Without the lock, two callers can each read
    `draft` and one of them then publishes: the loser's write reaches a published
    list, the DELETE removes nothing (the policy re-checks status per statement,
    so no rates are lost) and the INSERT is refused by RLS as SQLSTATE 42501 -
    which surfaced as a 500 rather than the 409 the contract promises.

    The lock closes the race; `_published_conflict` below turns the refusal into
    the right answer if anything ever reaches it another way.
    """
    row = (await db.execute(text(
        "SELECT id::text AS id, name, status::text AS status, effective_from, effective_to, "
        "       state_territory_id::text AS state_id, channel_tier::text AS tier "
        "FROM price_list WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"
        + (" FOR UPDATE" if for_update else "")),
        {"id": list_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such price list.")
    return row


PUBLISHED_LIST = ConflictError(
    "This list is published, so its rates can no longer change. Create a new list "
    "effective from the date the new rates start, and publish that.",
    code="price_list_published", fields={"id": "published"})


def _published_conflict(exc: DBAPIError) -> ConflictError | None:
    """An RLS refusal on `price_list_item` means the list is published: the INSERT
    policy is the draft-only one. 42501 from anywhere else is left alone."""
    if _sqlstate(exc) == "42501" and "price_list_item" in _pg_text(exc):
        return PUBLISHED_LIST
    return None


async def create_price_list(db: AsyncSession, body: sch.PriceListCreate) -> sch.PriceList:
    """Always a draft, and never provisional.

    `is_provisional` is not a request field. Rule 10 says only the loader sets it,
    and it said so while the schema accepted it from anyone with `pricing.edit` -
    so a genuine, client-confirmed list could be marked a stand-in and every
    quotation drawn from it would carry a warning telling the user not to send it.
    The loader writes SQL directly and is unaffected.
    """
    if body.state_territory_id:
        level = (await db.execute(text(
            "SELECT level::text FROM territory WHERE id = CAST(:t AS uuid) "
            "AND deleted_at IS NULL"), {"t": body.state_territory_id})).scalar_one_or_none()
        if level is None:
            raise ValidationFailed(fields={"state_territory_id": "No such territory."})
        if level != "state":
            raise ValidationFailed(fields={"state_territory_id": (
                f"A price list is scoped to a state; this is a {level}.")})
    if body.effective_to is not None and body.effective_to <= body.effective_from:
        raise ValidationFailed(fields={"effective_to": "Must be later than effective_from."})

    new_id: Any = (await db.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, effective_from, "
        "  effective_to, source_note, created_by) "
        "VALUES (:name, CAST(:state AS uuid), CAST(:tier AS channel_tier), CAST(:start AS date), "
        "  CAST(:finish AS date), :note, app_current_user_id()) RETURNING id::text"),
        {"name": body.name, "state": body.state_territory_id, "tier": body.channel_tier,
         "start": body.effective_from, "finish": body.effective_to,
         "note": body.source_note})).scalar_one()
    return await get_price_list(db, str(new_id))


async def patch_price_list(db: AsyncSession, list_id: str,
                           body: sch.PriceListPatch) -> sch.PriceList:
    """`effective_to` only, and forward only. A published list's rates never
    change: a correction is a new list (ADR-033), because editing one restates
    every past order that cited it."""
    row = await _raw_list(db, list_id)
    if body.effective_to <= row.effective_from:
        raise ValidationFailed(code="effective_to_not_forward",
                               fields={"effective_to": "Must be later than the list's own start."})
    if body.effective_to < today_ist():
        raise ValidationFailed(code="effective_to_not_forward", fields={
            "effective_to": "Must not be in the past: closing a list retrospectively would "
                            "change what past documents were priced from."})
    await db.execute(text(
        "UPDATE price_list SET effective_to = CAST(:d AS date), "
        "updated_by = app_current_user_id() WHERE id = CAST(:id AS uuid)"),
        {"d": body.effective_to, "id": list_id})
    return await get_price_list(db, list_id)


async def list_items(db: AsyncSession, list_id: str, *, q: str | None, unpriced: bool,
                     page: int, limit: int) -> sch.PriceListItemsPage:
    """Every product beside this list's rate for it, priced or not.

    A left join from the catalogue rather than a list of the rows present, because
    the screen's job is filling the gaps: "which of the 1,092 has no rate yet" is
    the question, and a list of what is already there cannot answer it.
    """
    await _raw_list(db, list_id)
    params: dict[str, Any] = {"id": list_id, "q": _like(q) if q else None,
                              "unpriced": unpriced, "limit": limit, "offset": (page - 1) * limit}
    rows = (await db.execute(text(r"""
SELECT count(*) OVER () AS total, p.id::text AS product_id, p.description::text AS description,
       u.code::text AS uom, i.rate AS rate, p.is_active AS is_active
FROM product p
JOIN uom u ON u.id = p.uom_id
LEFT JOIN price_list_item i ON i.price_list_id = CAST(:id AS uuid) AND i.product_id = p.id
WHERE p.deleted_at IS NULL
  AND (CAST(:q AS text) IS NULL OR p.description::text ILIKE CAST(:q AS text) ESCAPE '\')
  AND (NOT CAST(:unpriced AS boolean) OR (i.rate IS NULL AND p.is_active))
ORDER BY p.description, p.id
LIMIT :limit OFFSET :offset"""), params)).all()
    total = int(rows[0].total) if rows else 0
    return sch.PriceListItemsPage(
        data=[sch.PriceListItem(product_id=r.product_id, description=r.description, uom=r.uom,
                                rate=_opt(r.rate), is_active=r.is_active) for r in rows],
        meta=sch.OffsetMeta(page=page, limit=limit, total=total),
        unpriced=await _unpriced(db, list_id))


async def _unpriced(db: AsyncSession, list_id: str) -> int:
    """Active products this list holds no rate for."""
    return int((await db.execute(text(
        "SELECT count(*) FROM product p WHERE p.is_active AND p.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM price_list_item i "
        "                WHERE i.price_list_id = CAST(:id AS uuid) AND i.product_id = p.id)"),
        {"id": list_id})).scalar_one())


async def replace_items(db: AsyncSession, list_id: str,
                        body: sch.PriceListItemsPut) -> sch.PriceListItemsPage:
    """Replace a draft's rates wholesale. A product left out has no rate.

    Draft only. The DELETE policy already narrows to a draft's items, so a delete
    against a published list removes zero rows **silently** rather than raising,
    which is why the 409 comes from this status check and not from the database.
    """
    row = await _raw_list(db, list_id, for_update=True)
    if row.status != "draft":
        raise PUBLISHED_LIST

    seen: dict[str, int] = {}
    for i, item in enumerate(body.items):
        if item.product_id in seen:
            raise ValidationFailed(fields={
                f"items[{i}].product_id":
                    f"Sent twice; it is also items[{seen[item.product_id]}]."})
        seen[item.product_id] = i

    if body.items:
        known = {str(r[0]) for r in (await db.execute(text(
            "SELECT id::text FROM product WHERE id = ANY(CAST(:ids AS uuid[])) "
            "AND deleted_at IS NULL"), {"ids": list(seen)})).all()}
        unknown = {f"items[{i}].product_id": "No such product."
                   for pid, i in seen.items() if pid not in known}
        if unknown:
            raise ValidationFailed(fields=unknown)

    try:
        await db.execute(
            text("DELETE FROM price_list_item WHERE price_list_id = CAST(:id AS uuid)"),
            {"id": list_id})
        if body.items:
            await db.execute(text(
                "INSERT INTO price_list_item (price_list_id, product_id, rate) "
                "VALUES (CAST(:list AS uuid), CAST(:p AS uuid), :r)"),
                [{"list": list_id, "p": item.product_id, "r": item.rate} for item in body.items])
    except DBAPIError as exc:
        conflict = _published_conflict(exc)
        if conflict:
            raise conflict from exc
        raise
    return await list_items(db, list_id, q=None, unpriced=False, page=1, limit=100)


async def publish(db: AsyncSession, list_id: str, body: sch.PublishRequest) -> sch.PublishResult:
    """Publish a draft, closing the list it supersedes in the same transaction.

    **Close first, then publish.** Executed: publishing before closing raises the
    exclusion constraint, because for that instant two published lists cover the
    same scope and the same day. The constraints are deferrable so the pair can
    also be done the other way round, but the order is stated here rather than
    left to rely on that.

    The unpriced check is the one rev 1 got backwards. A successor created in
    March and half-filled would close the working list on 1 April and refuse every
    quotation touching the other 694 products. `allow_unpriced` is the deliberate
    override, and it needs `pricing.edit`.
    """
    row = await _raw_list(db, list_id, for_update=True)
    if row.status != "draft":
        raise ConflictError("This list is already published.",
                            code="price_list_published", fields={"id": "published"})

    gaps = await _unpriced(db, list_id)
    if gaps and not body.allow_unpriced:
        raise ConflictError(
            f"{gaps} active products have no rate in this list. Those lines would fall through "
            f"to a less specific list, or be refused. Add the rates, or publish with "
            f"allow_unpriced.", code="price_list_unpriced", fields={"unpriced_count": str(gaps)})

    overlapping = (await db.execute(text(
        "SELECT id::text AS id, name, effective_from, effective_to FROM price_list "
        "WHERE status = 'published' AND deleted_at IS NULL AND id <> CAST(:id AS uuid) "
        "AND state_territory_id IS NOT DISTINCT FROM CAST(:state AS uuid) "
        "AND channel_tier IS NOT DISTINCT FROM CAST(:tier AS channel_tier) "
        "AND daterange(effective_from, effective_to, '[)') "
        "    && daterange(CAST(:start AS date), CAST(:finish AS date), '[)') "
        "ORDER BY effective_from"),
        {"id": list_id, "state": row.state_id, "tier": row.tier,
         "start": row.effective_from, "finish": row.effective_to})).all()

    if len(overlapping) > 1:
        names = ", ".join(f"{o.name!r} from {o.effective_from}" for o in overlapping)
        raise ConflictError(
            f"More than one published list already covers this scope and these dates ({names}). "
            f"Close them first; publishing can only supersede one.",
            code="price_list_overlaps", fields={"effective_from": "overlaps more than one list"})

    closed: str | None = None
    if overlapping:
        other = overlapping[0]
        if other.effective_from >= row.effective_from:
            raise ConflictError(
                f"{other.name!r} already covers this scope from {other.effective_from}. A list "
                f"can only supersede one that started earlier; pick a later start date.",
                code="price_list_overlaps",
                fields={"effective_from": f"not later than {other.effective_from}"})
        # Superseding closes the predecessor at this list's start, which throws
        # away everything the predecessor covered *after* this list ends. A bounded
        # correction over an open-ended base list would leave the scope with no
        # list in force from the day the correction expires - executed: a list
        # covering June and July, published over one running from January with no
        # end, leaves September with nothing, and every quotation dated after it
        # refuses to price a scope that worked the day before.
        #
        # Refused rather than split. Splitting would resume the old rates after the
        # correction expires, and nobody has said that is what a bounded list
        # means (GAP-102).
        if row.effective_to is not None and (
                other.effective_to is None or other.effective_to > row.effective_to):
            covered = other.effective_to.isoformat() if other.effective_to else "with no end"
            raise ConflictError(
                f"{other.name!r} runs to {covered} and this list ends on {row.effective_to}. "
                f"Publishing it would leave this scope with no price list in force after "
                f"{row.effective_to}. Either leave this list open-ended, or publish a list "
                f"covering the rest of that period first.",
                code="price_list_gap",
                fields={"effective_to": f"would strand the scope after {row.effective_to}"})
        await db.execute(text(
            "UPDATE price_list SET effective_to = CAST(:d AS date), "
            "updated_by = app_current_user_id() WHERE id = CAST(:id AS uuid)"),
            {"d": row.effective_from, "id": other.id})
        closed = str(other.id)

    await db.execute(text(
        "UPDATE price_list SET status = 'published', published_at = now(), "
        "updated_by = app_current_user_id() WHERE id = CAST(:id AS uuid)"), {"id": list_id})
    return sch.PublishResult(price_list=await get_price_list(db, list_id),
                             closed_predecessor_id=closed, unpriced_count=gaps)


__all__ = [
    "MAX_DOCUMENT_TOTAL", "MAX_LINES", "assign_hsn", "create_price_list", "create_product",
    "get_price_list", "get_product", "hsn_history", "list_items", "list_price_lists",
    "list_products", "list_tax_rates", "load_products", "load_rates", "patch_price_list",
    "patch_product", "publish", "quote_lines", "replace_items", "resolve_scope", "seller_state",
    "set_tax_rate",
]
