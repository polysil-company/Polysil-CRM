"""Excel import (FS-062): store an uploaded sheet, check it against a mapping, commit.

The sheet is parsed once, at upload, and stored as text (`import_batch.rows`).
Check and commit read it back and run the same evaluation, so commit re-checks
inside its own transaction: masters may have changed since the person looked
(FS-062 section 4).

Nothing here commits. Partners are inserted one type tier per statement; rates
in one statement. The router owns the transaction (CLAUDE.md 4.1 rule 3).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from api.authz.predicate import Caller
from api.db import locks
from api.domain.imports import fields as import_fields
from api.domain.imports import products as product_rows
from api.domain.imports import template as import_template
from api.domain.imports.cells import key, name_key, redact
from api.domain.imports.reader import ImportUnreadableError, SheetRow, read_upload
from api.domain.imports.rows import (
    TYPE_ORDER,
    PartnerLookups,
    Place,
    ProductLookups,
    ProductRef,
    RowResult,
    finish_partners,
    parse_lines,
    parse_partners,
    parse_price_items,
)
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import imports as sch
from api.services.clock import today_ist
from api.services.pricing import PUBLISHED_LIST, _raw_list
from api.services.users import _pg_text, _sqlstate

MAX_ERROR_ROWS = 500
PREVIEW_ROWS = 20
SAMPLE_ROWS = 5
MAX_LINES = 200
STAFF_ONLY = ("partners", "price_list_items", "products")


# ── reading and writing the batch ────────────────────────────────────────────

_SELECT = """
SELECT id::text AS id, kind, status, target_id::text AS target_id, file_name, sheet, sheets,
       header_row, headers, rows, row_count, mapping, options, check_result, created_at
FROM import_batch WHERE id = CAST(:id AS uuid)
"""


async def _load(db: AsyncSession, batch_id: str, *, for_update: bool = False) -> Any:
    """The owner-only policy makes someone else's batch a 404, like a missing one."""
    row = (await db.execute(text(_SELECT + (" FOR UPDATE" if for_update else "")),
                            {"id": batch_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such import.")
    return row


def _sheet_rows(row: Any) -> list[SheetRow]:
    return [SheetRow(row=int(r["row"]), cells=tuple(r["cells"])) for r in (row.rows or [])]


def _out(row: Any, suggested: dict[str, int] | None = None) -> sch.ImportBatch:
    rows = row.rows or []
    return sch.ImportBatch(
        id=row.id, kind=row.kind, status=row.status, target_id=row.target_id,
        file_name=row.file_name, sheet=row.sheet, sheets=list(row.sheets or []),
        header_row=row.header_row, row_count=row.row_count, headers=list(row.headers),
        sample=[list(r["cells"]) for r in rows[:SAMPLE_ROWS]],
        fields=[sch.ImportField(key=f.key, label=f.label, required=f.required, help=f.help)
                for f in import_fields.FIELDS[row.kind]],
        suggested_mapping=suggested if suggested is not None else {},
        mapping=row.mapping, created_at=row.created_at,
        check=sch.ImportCheck.model_validate(row.check_result) if row.check_result else None)


PERMISSIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "partners": (("partners", "create"),),
    "price_list_items": (("pricing", "edit"),),
    "lines": (("sales_orders", "create"), ("quotations", "create")),
    # FS-083: the same permission as POST and PATCH /products
    "products": (("products", "edit"),),
}


async def _permit(db: AsyncSession, caller: Caller, kind: str) -> None:
    """Each kind has its own permission, known only once the kind is: any one of
    its pairs passes. Then the staff-only rule."""
    for module, action in PERMISSIONS[kind]:
        if (await db.execute(text("SELECT app_has_permission(:m, :a)"),
                             {"m": module, "a": action})).scalar_one():
            _staff_only(caller, kind)
            return
    raise ForbiddenError()


def _staff_only(caller: Caller, kind: str) -> None:
    """EC-18: dealers hold `partners.create`, but the import has none of the portal
    form's rules, so partner and price imports are staff only."""
    if kind in STAFF_ONLY and (caller.user_type != "staff" or caller.partner_id is not None):
        raise ForbiddenError()


async def template(db: AsyncSession, caller: Caller, kind: str) -> bytes:
    """FS-068: the blank file for a kind, to whoever may upload that kind."""
    await _permit(db, caller, kind)
    return await run_in_threadpool(import_template.template, kind)


async def _remembered(db: AsyncSession, kind: str) -> dict[str, str]:
    """The caller's last committed mapping of this kind, as field to header text. A
    discarded one is the mapping that did not work (FS-067 rule 4a). A line import is
    never committed, since the form saves its lines, so its last check counts."""
    last = (await db.execute(text(
        "SELECT headers, mapping FROM import_batch WHERE kind = :k AND mapping IS NOT NULL "
        "AND status = ANY(CAST(:done AS text[])) AND created_by = app_current_user_id() "
        "ORDER BY created_at DESC LIMIT 1"),
        {"k": kind, "done": ["checked", "committed"] if kind == "lines" else ["committed"]}
    )).one_or_none()
    if last is None:
        return {}
    headers = list(last.headers)
    return {f: headers[i] for f, i in dict(last.mapping).items()
            if isinstance(i, int) and 0 <= i < len(headers)}


async def upload(db: AsyncSession, caller: Caller, *, kind: str, target_id: str | None,
                 file_name: str, data: bytes, sha256: str, sheet: str | None,
                 header_row: int | None) -> sch.ImportBatch:
    await _permit(db, caller, kind)
    if kind == "price_list_items":
        if not target_id:
            raise ValidationFailed(fields={"target_id": "the draft price list to fill"})
        if (await _raw_list(db, target_id)).status != "draft":
            raise PUBLISHED_LIST
    elif target_id:
        raise ValidationFailed(fields={"target_id": "only a price import has a target"})
    try:
        # openpyxl is CPU-bound: a 5,000-row sheet takes a second or more, which must
        # not stall every other request on this worker (code review F-3)
        parsed = await run_in_threadpool(read_upload, data, file_name, sheet=sheet,
                                         header_row=header_row,
                                         score=import_fields.header_score(kind))
    except ImportUnreadableError as exc:
        raise ValidationFailed(str(exc), code=exc.code, fields={exc.field: str(exc)}) from exc

    new_id = (await db.execute(text(
        "INSERT INTO import_batch (kind, target_id, file_name, file_sha256, sheet, sheets, "
        "  header_row, headers, rows, row_count, created_by) "
        "VALUES (:kind, CAST(:target AS uuid), :name, :sha, :sheet, CAST(:sheets AS jsonb), "
        "  :hr, CAST(:headers AS jsonb), CAST(:rows AS jsonb), :n, app_current_user_id()) "
        "RETURNING id::text"), {
            "kind": kind, "target": target_id, "name": (file_name or "upload")[:255],
            "sha": sha256, "sheet": parsed.sheet, "sheets": json.dumps(parsed.sheets),
            "hr": parsed.header_row, "headers": json.dumps(parsed.headers),
            "rows": json.dumps([{"row": r.row, "cells": list(r.cells)} for r in parsed.rows]),
            "n": len(parsed.rows)})).scalar_one()
    row = await _load(db, str(new_id))
    return _out(row, import_fields.suggest(kind, parsed.headers, await _remembered(db, kind),
                                           empty=_empty_columns(parsed.rows, len(parsed.headers))))


async def get(db: AsyncSession, batch_id: str) -> sch.ImportBatch:
    row = await _load(db, batch_id)
    suggested = (import_fields.suggest(
        row.kind, list(row.headers), await _remembered(db, row.kind),
        empty=_empty_columns(_sheet_rows(row), len(row.headers)))
        if row.status != "discarded" else {})
    return _out(row, suggested)


# ── evaluating the rows ──────────────────────────────────────────────────────

@dataclass
class Evaluation:
    results: list[RowResult]
    column_warnings: dict[str, str]
    # FS-083 EC-12: the day this evaluation read. At commit it is the commit's own
    # re-check, so the HSN rows open on the day whose rates and guards were checked
    today: dt.date | None = None


def _empty_columns(rows: Sequence[SheetRow], width: int) -> set[int]:
    """Columns with no value on any row. Empty when there are no rows at all."""
    if not rows:
        return set()
    return {c for c in range(width) if not any(c < len(r.cells) and r.cells[c] for r in rows)}


def _column_warnings(rows: Sequence[SheetRow], mapping: dict[str, int]) -> dict[str, str]:
    """EC-16: a mapped column with nothing in it is one message, not a row each."""
    out = {}
    empty = _empty_columns(rows, max(mapping.values(), default=-1) + 1)
    for field_key, col in mapping.items():
        if col in empty:
            out[field_key] = ("This column is empty on every row, or holds formulas with no "
                              "saved result. Open the file in Excel, save it, and upload again.")
    return out


async def _partner_lookups(db: AsyncSession) -> PartnerLookups:
    states: dict[str, Place] = {}
    districts: dict[tuple[str, str], Place] = {}
    for r in (await db.execute(text(
            "SELECT t.id::text, t.name, t.code::text FROM territory t "
            "WHERE t.deleted_at IS NULL AND t.level = 'state'"))).all():
        place = Place(r[0], r[1])
        states.setdefault(key(r[1]), place)
        if r[2]:
            states.setdefault(key(r[2]), place)
    for r in (await db.execute(text(
            "SELECT t.id::text, t.name, t.parent_id::text FROM territory t "
            "WHERE t.deleted_at IS NULL AND t.level = 'district'"))).all():
        districts.setdefault((r[2], key(r[1])), Place(r[0], r[1]))
    return PartnerLookups(states=states, districts=districts)


async def _outside(db: AsyncSession, territory_ids: set[str]) -> set[str]:
    """EC-10 and plan review C-4: ask the real insert policy. A placeholder partner
    is inserted per territory inside a savepoint and rolled back; 42501 means the
    caller may not place a partner there. No second copy of the policy to drift."""
    out: set[str] = set()
    for tid in sorted(territory_ids):
        probe = "import-probe-" + uuid.uuid4().hex[:12]
        savepoint = await db.begin_nested()
        try:
            await db.execute(text(
                "INSERT INTO channel_partner (partner_type, code, name, territory_id, "
                "  price_tier, created_by) "
                "VALUES ('distributor', :c, 'import probe', CAST(:t AS uuid), 'distributor', "
                "  app_current_user_id())"), {"c": probe, "t": tid})
        except DBAPIError as exc:
            if _sqlstate(exc) != "42501":
                raise
            out.add(tid)
        finally:
            await savepoint.rollback()
    return out


async def _evaluate_partners(db: AsyncSession, rows: list[SheetRow],
                             mapping: dict[str, int]) -> list[RowResult]:
    results = parse_partners(rows, mapping, await _partner_lookups(db))
    codes = sorted({v for r in results if (v := r.values.get("code"))})
    taken = {str(c).casefold() for c in (await db.execute(text(
        "SELECT partner_codes_taken(CAST(:c AS citext[]))"), {"c": codes})).scalars().all()}
    parents = sorted({v for r in results if (v := r.values.get("parent_code"))})
    existing = {str(r[0]).casefold(): (str(r[1]), str(r[2])) for r in (await db.execute(text(
        "SELECT code::text, id::text, partner_type::text FROM channel_partner "
        "WHERE code = ANY(CAST(:c AS citext[])) AND deleted_at IS NULL"),
        {"c": parents})).all()}
    places = {t for r in results if (t := r.values.get("territory_id"))}
    finish_partners(results, taken=taken, outside=await _outside(db, places), existing=existing)
    return results


async def _product_lookups(db: AsyncSession) -> ProductLookups:
    """Every product not deleted, once per check or commit. Names are compared after
    `name_key`, which SQL cannot index, so the catalogue is keyed here: 1,092 rows
    on production (FS-067 rule 5)."""
    found = (await db.execute(text(
        "SELECT p.id::text, p.description::text, p.item_code::text, p.is_active, u.code::text, "
        "       u.decimals, p.pack_multiple "
        "FROM product p JOIN uom u ON u.id = p.uom_id WHERE p.deleted_at IS NULL"))).all()
    return ProductLookups.build(
        ProductRef(id=r[0], description=r[1], item_code=r[2], is_active=r[3], uom_code=r[4],
                   uom_decimals=int(r[5]),
                   pack_multiple=Decimal(r[6]) if r[6] is not None else None)
        for r in found)


async def _catalogue_lookups(db: AsyncSession) -> product_rows.CatalogueLookups:
    """FS-083: the whole catalogue as it stands today, with each product's HSN in
    force, its start, and whether a later one is queued. Deleted products are read
    only for their description and code, which the unique indexes still hold."""
    today = today_ist()
    found = (await db.execute(text("""
SELECT p.id::text, p.description::text, p.item_code::text, p.is_active, u.code::text, u.decimals,
       p.pack_multiple, p.deleted_at IS NOT NULL AS deleted, c.id::text, c.code::text,
       p.quotation_category::text, u.id::text, p.mrp, p.is_subsidy_eligible,
       h.hsn_code, h.effective_from, p.provisional_fields,
       -- deleted rows too: ex_product_hsn covers them (plan review N-9)
       EXISTS (SELECT 1 FROM product_hsn l WHERE l.product_id = p.id
               AND l.effective_from > CAST(:d AS date)) AS later
FROM product p
JOIN uom u ON u.id = p.uom_id
JOIN product_category c ON c.id = p.product_category_id
LEFT JOIN product_hsn h ON h.product_id = p.id AND h.deleted_at IS NULL
     AND daterange(h.effective_from, h.effective_to, '[)') @> CAST(:d AS date)"""),
        {"d": today})).all()
    refs = []
    current: dict[str, product_rows.Current] = {}
    descriptions: dict[str, str] = {}
    codes: dict[str, str] = {}
    deleted: set[str] = set()
    for r in found:
        # EC-1: by name_key, which is stricter than the citext unique index
        descriptions[name_key(r[1])] = r[0]
        if r[2]:
            codes[name_key(r[2])] = r[0]
        if r[7]:
            deleted.add(r[0])
            continue
        ref = ProductRef(id=r[0], description=r[1], item_code=r[2], is_active=r[3],
                         uom_code=r[4], uom_decimals=int(r[5]),
                         pack_multiple=Decimal(r[6]) if r[6] is not None else None)
        refs.append(ref)
        current[r[0]] = product_rows.Current(
            ref=ref, category=product_rows.Master(r[8], r[9]), quotation_category=r[10],
            uom=product_rows.Master(r[11], r[4]),
            mrp=Decimal(r[12]) if r[12] is not None else None,
            pack_multiple=ref.pack_multiple, is_subsidy_eligible=r[13], hsn_code=r[14],
            hsn_from=r[15], hsn_later=r[17], provisional=frozenset(r[16] or []))
    masters: dict[str, dict[str, product_rows.Master]] = {}
    for table in ("product_category", "uom"):
        found_masters = (await db.execute(text(
            f"SELECT id::text, code::text, name FROM {table} "
            "WHERE deleted_at IS NULL AND is_active ORDER BY code"))).all()
        named: dict[str, product_rows.Master] = {}
        # a code wins over another master's name
        for r in found_masters:
            named.setdefault(key(r[1]), product_rows.Master(r[0], r[1]))
        for r in found_masters:
            named.setdefault(key(r[2]), product_rows.Master(r[0], r[1]))
        masters[table] = named
    hsn_rows: Sequence[Any] = (await db.execute(text(
        "SELECT DISTINCT hsn_code FROM gst_rate WHERE is_active AND deleted_at IS NULL "
        "AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date)"),
        {"d": today})).scalars().all()
    rated = frozenset(str(h) for h in hsn_rows)
    return product_rows.CatalogueLookups(
        products=ProductLookups.build(refs), current=current,
        categories=masters["product_category"], uoms=masters["uom"], rated_hsn=rated,
        today=today, descriptions=descriptions, codes=codes, deleted=frozenset(deleted))


# EC-5: the client's sheet has no item codes, so a corrected spelling arrives as a
# new product. pg_trgm similarity; 0.8 catches one or two letters in a long name.
NEAR = 0.8


async def _near_names(db: AsyncSession, results: list[RowResult]) -> None:
    """A new row whose description is close to an existing product's gets a note
    naming it. It still imports: only the admin knows whether it is a new product
    or a spelling fix (GAP-561)."""
    new = {r.row: r.values["product"] for r in results
           if r.ok and r.values.get("action") == "new"}
    if not new:
        return
    found = (await db.execute(text("""
SELECT x.row, n.description
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(row int, d text)
CROSS JOIN LATERAL (
    SELECT p.description::text AS description FROM product p
    WHERE p.deleted_at IS NULL AND similarity(p.description::text, x.d) >= :near
    ORDER BY similarity(p.description::text, x.d) DESC, p.description LIMIT 1) n"""),
        {"rows": json.dumps([{"row": k, "d": v} for k, v in new.items()]),
         "near": NEAR})).all()
    by_row = {r.row: r for r in results}
    for row, description in found:
        by_row[int(row)].values["near"] = description
        by_row[int(row)].notes["description"] = f"close to {description!r}"


def _product_warnings(results: list[RowResult]) -> dict[str, str]:
    """FS-083 rule 12: a new product cannot be quoted until it has an HSN code and a
    rate. Said once for the column, not on every row. Open drafts using a product
    switched off are not counted yet (GAP-563)."""
    new = [r for r in results if r.ok and r.values.get("action") == "new"]
    out = {}
    near = sum(1 for r in new if r.values.get("near"))
    still_off = sum(1 for r in results if r.ok and r.notes.get("is_active"))
    untaxed = sum(1 for r in new if not r.values["write"]["hsn_code"])
    if untaxed:
        out["hsn_code"] = (f"{untaxed} new product{'s have' if untaxed > 1 else ' has'} no HSN "
                           f"code. {'They' if untaxed > 1 else 'It'} cannot be quoted until "
                           f"one is set on the product page.")
    msgs = []
    if near:
        msgs.append(f"{near} new product{'s are' if near > 1 else ' is'} close to an existing "
                    f"name. If {'they are' if near > 1 else 'it is'} a spelling fix, give the "
                    f"item code or change the name on the product page instead.")
    if new:
        msgs.append(f"{len(new)} new product{'s have' if len(new) > 1 else ' has'} no rate "
                    f"yet. Add {'them' if len(new) > 1 else 'it'} to a price list with a price "
                    f"import before quoting.")
    if msgs:
        out["description"] = " ".join(msgs)
    if still_off:
        # EC-9
        out["is_active"] = (f"{still_off} row{'s match' if still_off > 1 else ' matches'} a "
                            f"switched-off product. Set Active to yes to sell "
                            f"{'them' if still_off > 1 else 'it'} again.")
    return out


async def _evaluate(db: AsyncSession, kind: str, rows: list[SheetRow],
                    mapping: dict[str, int], *, at_commit: bool = False) -> Evaluation:
    if kind == "products":
        lk = await _catalogue_lookups(db)
        results = product_rows.parse_products(rows, mapping, lk)
        if not at_commit:
            # a note for the person; commit does not need it (plan review N-8)
            await _near_names(db, results)
        warnings = _column_warnings(rows, mapping)
        for k, msg in _product_warnings(results).items():
            warnings.setdefault(k, msg)
        return Evaluation(results, warnings, today=lk.today)
    if kind == "partners":
        results = await _evaluate_partners(db, rows, mapping)
    elif kind == "price_list_items":
        results = parse_price_items(rows, mapping, await _product_lookups(db))
    else:
        results = parse_lines(rows, mapping, await _product_lookups(db))
    warnings = _column_warnings(rows, mapping)
    by_name = sum(1 for r in results if r.ok and r.notes.get("item_code"))
    if by_name:
        # FS-067 rule 6 b: good rows, said once for the column
        warnings.setdefault("item_code", (
            "1 item code is not in the catalogue. That row was matched by its description."
            if by_name == 1 else
            f"{by_name} item codes are not in the catalogue. Those rows were matched by "
            f"their description."))
    return Evaluation(results, warnings)


def _preview_values(kind: str, values: dict[str, Any]) -> dict[str, object]:
    if kind == "products":
        return {k: v for k, v in values.items() if k != "write"}
    hidden = {"territory_id", "territory_field", "parent_row", "parent_id"}
    return {k: v for k, v in values.items() if k not in hidden and v is not None} \
        if kind == "partners" else dict(values)


def _summary(kind: str, ev: Evaluation) -> sch.ImportCheck:
    bad = [r for r in ev.results if not r.ok]
    good = [r for r in ev.results if r.ok]
    counts = None
    shown = good
    if kind == "products":
        counts = sch.ProductImportCounts(**product_rows.change_counts(ev.results),
                                         fingerprint=product_rows.fingerprint(ev.results))
        # FS-083: the preview is the rows that change something, renames and
        # switch-offs first (EC-7)
        shown = sorted((r for r in good if r.values["action"] != "unchanged"),
                       key=product_rows.preview_order)
    lines = None
    if kind == "lines":
        lines = [sch.ImportLine(row=r.row, **{k: r.values[k] for k in (
            "product_id", "product", "qty", "discount_pct", "discount2_pct", "discount3_pct")})
            for r in good]
    return sch.ImportCheck(
        total=len(ev.results), ok=len(good), errors=len(bad),
        error_rows=[sch.ImportRowError(row=r.row, errors=r.errors) for r in bad[:MAX_ERROR_ROWS]],
        preview=[sch.ImportPreviewRow(row=r.row, values=_preview_values(kind, r.values))
                 for r in shown[:PREVIEW_ROWS]],
        column_warnings=ev.column_warnings, lines=lines, products=counts)


def _open(row: Any) -> None:
    if row.status in ("committed", "discarded"):
        raise ConflictError(f"This import is {row.status}. Upload the file again.",
                            code="import_wrong_state", fields={"status": row.status})


async def check(db: AsyncSession, caller: Caller, batch_id: str,
                body: sch.ImportCheckRequest) -> sch.ImportCheck:
    row = await _load(db, batch_id, for_update=True)
    await _permit(db, caller, row.kind)
    _open(row)
    problems = import_fields.mapping_problems(row.kind, body.mapping, len(row.headers))
    if problems:
        raise ValidationFailed("Fix the column matches.", fields=problems)
    if row.kind == "price_list_items" and (await _raw_list(db, row.target_id)).status != "draft":
        raise PUBLISHED_LIST
    ev = await _evaluate(db, row.kind, _sheet_rows(row), body.mapping)
    result = _summary(row.kind, ev)
    if row.kind == "lines" and result.ok > MAX_LINES:
        raise ValidationFailed(f"A document holds at most {MAX_LINES} lines; this sheet has "
                               f"{result.ok}.", code="import_too_many_rows",
                               fields={"file": f"at most {MAX_LINES} lines"})
    await db.execute(text(
        "UPDATE import_batch SET mapping = CAST(:m AS jsonb), options = CAST(:o AS jsonb), "
        "  check_result = CAST(:c AS jsonb), status = 'checked' WHERE id = CAST(:id AS uuid)"),
        {"id": batch_id, "m": json.dumps(body.mapping), "o": body.options.model_dump_json(),
         "c": result.model_dump_json()})
    return result


def _kept_check(kind: str, stored: Any) -> str | None:
    """FS-067 rule 9: what a discarded batch keeps of its check, in the full
    `ImportCheck` shape so GET still reads it. Partner errors can quote a mobile, so
    a partner batch keeps counts only. Product errors keep their reasons with the
    quoted cell taken out: a misfiled staff sheet must not leave names behind."""
    if not stored:
        return None
    check = sch.ImportCheck.model_validate(stored)
    check.preview = []
    check.lines = None
    if kind == "partners":
        check.error_rows = []
        check.column_warnings = {}
    else:
        check.error_rows = [sch.ImportRowError(row=e.row, errors={
            k: redact(v) for k, v in e.errors.items()}) for e in check.error_rows]
    return check.model_dump_json()


async def discard(db: AsyncSession, batch_id: str) -> None:
    row = await _load(db, batch_id, for_update=True)
    _open(row)
    await db.execute(text(
        "UPDATE import_batch SET status = 'discarded', rows = NULL, "
        "  check_result = CAST(:c AS jsonb) WHERE id = CAST(:id AS uuid)"),
        {"id": batch_id, "c": _kept_check(row.kind, row.check_result)})


# ── commit ───────────────────────────────────────────────────────────────────

_CODE_IN_DETAIL = re.compile(r"Key \(code\)=\((?P<code>[^)]*)\)")


async def commit(db: AsyncSession, caller: Caller, batch_id: str,
                 body: sch.ImportCommitRequest) -> sch.ImportCommitResult:
    row = await _load(db, batch_id, for_update=True)
    await _permit(db, caller, row.kind)
    _open(row)
    if row.kind == "lines":
        raise ConflictError("A line import is not saved here: the order or quotation form "
                            "saves its lines.", code="import_wrong_state",
                            fields={"kind": "lines"})
    if row.status != "checked" or row.mapping is None:
        raise ConflictError("Check the import before saving it.", code="import_wrong_state",
                            fields={"status": row.status})
    mapping = dict(row.mapping)
    # EC-19: lock the list as publish() does, then decide from its status
    if row.kind == "price_list_items" and (
            await _raw_list(db, row.target_id, for_update=True)).status != "draft":
        raise PUBLISHED_LIST
    if row.kind == "products":
        # EC-11: one product import commits at a time, and the product page's
        # edits wait for it (code review F-1). Taken before the re-read below
        await db.execute(text(locks.PRODUCT_CATALOGUE))
    ev = await _evaluate(db, row.kind, _sheet_rows(row), mapping, at_commit=True)
    if row.kind == "products":
        _same_as_checked(row.check_result, ev)
    good = [r for r in ev.results if r.ok]
    bad = len(ev.results) - len(good)
    if bad and not body.skip_invalid:
        result = _summary(row.kind, ev)
        raise ValidationFailed(
            f"{bad} rows have errors. Fix them, or import the good rows only.",
            code="import_has_errors",
            fields={f"rows[{e.row}].{k}": v
                    for e in result.error_rows for k, v in e.errors.items()})
    if not good:
        raise ValidationFailed("No row can be imported.", code="import_has_errors",
                               fields={"rows": "none are good"})

    updated = unchanged = 0
    if row.kind == "partners":
        created = await _commit_partners(db, caller, good)
        target = None
    elif row.kind == "products":
        created, updated, unchanged = await _commit_products(db, good, ev.today or today_ist())
        target = None
    else:
        options = dict(row.options or {})
        created = await _commit_rates(db, row.target_id, good,
                                      merge=options.get("mode") == "merge")
        target = row.target_id
    stored = _summary(row.kind, ev)
    if row.kind == "partners":
        stored.preview = []   # FS-067 rule 9b: mobiles, GSTINs and PANs
    await db.execute(text(
        "UPDATE import_batch SET status = 'committed', committed_at = now(), "
        "  check_result = CAST(:c AS jsonb) WHERE id = CAST(:id AS uuid)"),
        {"id": batch_id, "c": stored.model_dump_json()})
    return sch.ImportCommitResult(status="committed", created=created, skipped=bad,
                                  price_list_id=target, updated=updated, unchanged=unchanged)


async def _commit_partners(db: AsyncSession, caller: Caller, good: list[RowResult]) -> int:
    """Plan review C-5: one INSERT per type tier, parents first, then one statement
    for the events. Ids are made here so a dealer can name a distributor on an
    earlier row of the same file. No login is created (rule 3)."""
    ids = {r.row: str(uuid.uuid4()) for r in good}
    by_row = {r.row: r for r in good}
    created = 0
    for ptype in TYPE_ORDER:
        tier = [r for r in good if r.values["partner_type"] == ptype]
        if not tier:
            continue
        records = []
        for r in tier:
            v = r.values
            parent = ids[v["parent_row"]] if v.get("parent_row") in ids else v.get("parent_id")
            records.append({
                "id": ids[r.row], "parent_id": parent, "partner_type": ptype, "code": v["code"],
                "name": v["name"], "territory_id": v["territory_id"],
                "contact_name": v["contact_name"], "mobile": v["mobile"], "email": v["email"],
                "address": v["address"], "gstin": v["gstin"], "pan": v["pan"],
                "is_gst_registered": v["is_gst_registered"], "credit_limit": v["credit_limit"],
                "payment_terms_days": v["payment_terms_days"]})
        try:
            async with db.begin_nested():
                await db.execute(text("""
INSERT INTO channel_partner (id, parent_id, partner_type, code, name, territory_id, contact_name,
    mobile, email, address, gstin, pan, is_gst_registered, price_tier, credit_limit,
    payment_terms_days, created_by)
SELECT x.id, x.parent_id, CAST(x.partner_type AS partner_type), CAST(x.code AS citext), x.name,
       x.territory_id, x.contact_name, x.mobile, CAST(x.email AS citext), x.address, x.gstin,
       x.pan, x.is_gst_registered, CAST(x.partner_type AS channel_tier), x.credit_limit,
       x.payment_terms_days, app_current_user_id()
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(id uuid, parent_id uuid, partner_type text,
    code text, name text, territory_id uuid, contact_name text, mobile text, email text,
    address text, gstin text, pan text, is_gst_registered boolean, credit_limit numeric,
    payment_terms_days int)"""), {"rows": json.dumps(records)})
        except DBAPIError as exc:
            raise _late_refusal(exc, tier) from exc
        created += len(tier)

    await db.execute(text("""
INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload)
SELECT 'channel_partner', x.id, x.id, 'partner.created', app_current_user_id(),
       jsonb_build_object('code', x.code, 'partner_type', x.partner_type,
                          'parent_id', x.parent_id, 'via', 'import')
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(id uuid, code text, partner_type text,
    parent_id uuid)"""), {"rows": json.dumps([
        {"id": ids[r.row], "code": by_row[r.row].values["code"],
         "partner_type": r.values["partner_type"],
         "parent_id": (ids[r.values["parent_row"]] if r.values.get("parent_row") in ids
                       else r.values.get("parent_id"))} for r in good])})
    return created


def _late_refusal(exc: DBAPIError, tier: list[RowResult]) -> Exception:
    """A clash the check could not see (a code taken a moment ago), named by row."""
    state = _sqlstate(exc)
    if state == "23505":
        # asyncpg keeps "Key (code)=(X)" in the detail, not the message (code review F-1)
        found = _CODE_IN_DETAIL.search(getattr(exc.orig, "detail", None) or _pg_text(exc))
        code = found.group("code").casefold() if found else None
        rows = [r.row for r in tier if code and r.values["code"].casefold() == code]
        where = f"rows[{rows[0]}].code" if rows else "rows"
        return ValidationFailed("A partner code was taken since the check.",
                                code="import_has_errors",
                                fields={where: "already in use"})
    if state == "42501":
        return ValidationFailed("A row is outside your area.", code="import_has_errors",
                                fields={"rows": "outside your area; check again"})
    if state == "23514":
        # channel_partner_type_order(): a parent closed or retyped since the check
        # (code review F-4)
        with_parent = [r.row for r in tier if r.values.get("parent_id")]
        where = f"rows[{with_parent[0]}].parent_code" if len(with_parent) == 1 else "rows"
        return ValidationFailed("A parent partner changed since the check. Check again.",
                                code="import_has_errors", fields={where: _pg_text(exc)})
    return exc


async def _commit_rates(db: AsyncSession, list_id: str, good: list[RowResult], *,
                        merge: bool) -> int:
    """`price_list_item` has no UPDATE grant, so merge deletes the file's products and
    inserts them; replace deletes everything first. The list is locked by the caller."""
    items = [{"p": r.values["product_id"], "r": r.values["rate"]} for r in good]
    try:
        if merge:
            await db.execute(text(
                "DELETE FROM price_list_item WHERE price_list_id = CAST(:l AS uuid) "
                "AND product_id = ANY(CAST(:ps AS uuid[]))"),
                {"l": list_id, "ps": [i["p"] for i in items]})
        else:
            await db.execute(text(
                "DELETE FROM price_list_item WHERE price_list_id = CAST(:l AS uuid)"),
                {"l": list_id})
        await db.execute(text(
            "INSERT INTO price_list_item (price_list_id, product_id, rate) "
            "SELECT CAST(:l AS uuid), x.p, x.r "
            "FROM jsonb_to_recordset(CAST(:items AS jsonb)) AS x(p uuid, r numeric)"),
            {"l": list_id, "items": json.dumps(items)})
    except DBAPIError as exc:
        if _sqlstate(exc) == "42501" and "price_list_item" in _pg_text(exc):
            raise PUBLISHED_LIST from exc
        raise
    return len(items)


def _same_as_checked(stored: Any, ev: Evaluation) -> None:
    """EC-11: the catalogue changed between check and commit, say by an edit on the
    product page. Saving now would write what nobody looked at, or undo that edit,
    so the person checks again. Compared by a fingerprint of every row's action
    and changes, not the counts: two edits can cancel out (plan review N-2)."""
    if not stored:
        return
    before = sch.ImportCheck.model_validate(stored)
    if before.products is None or before.products.fingerprint != product_rows.fingerprint(
            ev.results):
        raise ConflictError("The catalogue changed since the check. Check again.",
                            code="import_wrong_state", fields={"status": "check again"})


async def _commit_products(db: AsyncSession, good: list[RowResult],
                           today: dt.date) -> tuple[int, int, int]:
    """FS-083: new products in one INSERT, changed ones in one UPDATE, then the HSN
    rows. An update sends only its changed columns; null keeps the catalogue's
    value. Setting MRP, pack multiple or HSN clears that provisional mark (rules 9,
    10). Audit rows come from `audit_row()`; products have no activity_event (FS-010
    rule 15)."""
    new = []
    hsn: list[dict[str, str]] = []
    for r in good:
        if r.values["action"] != "new":
            continue
        w = dict(r.values["write"])
        w["id"] = str(uuid.uuid4())
        new.append(w)
        if w["hsn_code"]:
            hsn.append({"p": w["id"], "h": w["hsn_code"]})
    changed = [dict(r.values["write"]) for r in good if r.values["action"] == "update"]
    for w in changed:
        w["cleared"] = [c for c in ("mrp", "pack_multiple") if c in w] + (
            ["hsn_code", "gst_slab"] if "hsn_code" in w else []) + w.pop("confirm", [])
        if "hsn_code" in w:
            hsn.append({"p": w["id"], "h": w["hsn_code"]})
    try:
        async with db.begin_nested():
            if new:
                await db.execute(text("""
INSERT INTO product (id, description, item_code, product_category_id, quotation_category, uom_id,
    mrp, pack_multiple, is_subsidy_eligible, is_active, created_by)
SELECT x.id, CAST(x.description AS citext), CAST(x.item_code AS citext), x.category_id,
       CAST(x.quotation_category AS quotation_category), x.uom_id, x.mrp, x.pack_multiple,
       x.is_subsidy_eligible, x.is_active, app_current_user_id()
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(id uuid, description text, item_code text,
    category_id uuid, quotation_category text, uom_id uuid, mrp numeric, pack_multiple numeric,
    is_subsidy_eligible boolean, is_active boolean)"""), {"rows": json.dumps(new)})
            if changed:
                await db.execute(text("""
UPDATE product p SET
    description = COALESCE(CAST(x.description AS citext), p.description),
    item_code = COALESCE(CAST(x.item_code AS citext), p.item_code),
    product_category_id = COALESCE(x.category_id, p.product_category_id),
    quotation_category = COALESCE(CAST(x.quotation_category AS quotation_category),
                                  p.quotation_category),
    uom_id = COALESCE(x.uom_id, p.uom_id),
    mrp = COALESCE(x.mrp, p.mrp),
    pack_multiple = COALESCE(x.pack_multiple, p.pack_multiple),
    is_subsidy_eligible = COALESCE(x.is_subsidy_eligible, p.is_subsidy_eligible),
    is_active = COALESCE(x.is_active, p.is_active),
    -- untouched unless a mark it holds is cleared, and in its own order: the audit
    -- row must not show a change that did not happen (plan review N-3, review F-3)
    provisional_fields = CASE WHEN p.provisional_fields && x.cleared
        THEN ARRAY(SELECT f FROM unnest(p.provisional_fields) WITH ORDINALITY AS u(f, n)
                   WHERE f <> ALL(x.cleared) ORDER BY n)
        ELSE p.provisional_fields END,
    updated_by = app_current_user_id()
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(id uuid, description text, item_code text,
    category_id uuid, quotation_category text, uom_id uuid, mrp numeric, pack_multiple numeric,
    is_subsidy_eligible boolean, is_active boolean, hsn_code text, cleared text[])
WHERE p.id = x.id AND p.deleted_at IS NULL"""), {"rows": json.dumps(changed)})
            if hsn:
                # rule 9: the row in force closes today and the new one starts today.
                # The check refused a product whose row started today or that has a
                # later one.
                await db.execute(text("""
UPDATE product_hsn h SET effective_to = CAST(:d AS date), updated_by = app_current_user_id()
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(p uuid, h text)
WHERE h.product_id = x.p AND h.deleted_at IS NULL AND h.effective_from < CAST(:d AS date)
  AND (h.effective_to IS NULL OR h.effective_to > CAST(:d AS date))"""),
                    {"rows": json.dumps(hsn), "d": today})
                await db.execute(text("""
INSERT INTO product_hsn (product_id, hsn_code, effective_from, created_by)
SELECT x.p, x.h, CAST(:d AS date), app_current_user_id()
FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(p uuid, h text)"""),
                    {"rows": json.dumps(hsn), "d": today})
    except DBAPIError as exc:
        if _sqlstate(exc) in ("23505", "23P01"):
            raise ValidationFailed("A product changed since the check. Check again.",
                                   code="import_has_errors",
                                   fields={"rows": "a product changed since the check"}
                                   ) from exc
        raise
    unchanged = sum(1 for r in good if r.values["action"] == "unchanged")
    return len(new), len(changed), unchanged
