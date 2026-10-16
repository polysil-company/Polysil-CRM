"""Excel import (FS-062): store an uploaded sheet, check it against a mapping, commit.

The sheet is parsed once, at upload, and stored as text (`import_batch.rows`).
Check and commit read it back and run the same evaluation, so commit re-checks
inside its own transaction: masters may have changed since the person looked
(FS-062 section 4).

Nothing here commits. Partners are inserted one type tier per statement; rates
in one statement. The router owns the transaction (CLAUDE.md 4.1 rule 3).
"""

from __future__ import annotations

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
from api.domain.imports import fields as import_fields
from api.domain.imports.cells import key, redact
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
from api.services.pricing import PUBLISHED_LIST, _raw_list
from api.services.users import _pg_text, _sqlstate

MAX_ERROR_ROWS = 500
PREVIEW_ROWS = 20
SAMPLE_ROWS = 5
MAX_LINES = 200
STAFF_ONLY = ("partners", "price_list_items")


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
        field = {"validation_error": "sheet" if sheet else "header_row"}.get(exc.code, "file")
        raise ValidationFailed(str(exc), code=exc.code, fields={field: str(exc)}) from exc

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


async def _evaluate(db: AsyncSession, kind: str, rows: list[SheetRow],
                    mapping: dict[str, int]) -> Evaluation:
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
    hidden = {"territory_id", "territory_field", "parent_row", "parent_id"}
    return {k: v for k, v in values.items() if k not in hidden and v is not None} \
        if kind == "partners" else dict(values)


def _summary(kind: str, ev: Evaluation) -> sch.ImportCheck:
    bad = [r for r in ev.results if not r.ok]
    good = [r for r in ev.results if r.ok]
    lines = None
    if kind == "lines":
        lines = [sch.ImportLine(row=r.row, **{k: r.values[k] for k in (
            "product_id", "product", "qty", "discount_pct", "discount2_pct", "discount3_pct")})
            for r in good]
    return sch.ImportCheck(
        total=len(ev.results), ok=len(good), errors=len(bad),
        error_rows=[sch.ImportRowError(row=r.row, errors=r.errors) for r in bad[:MAX_ERROR_ROWS]],
        preview=[sch.ImportPreviewRow(row=r.row, values=_preview_values(kind, r.values))
                 for r in good[:PREVIEW_ROWS]],
        column_warnings=ev.column_warnings, lines=lines)


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
    ev = await _evaluate(db, row.kind, _sheet_rows(row), mapping)
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

    if row.kind == "partners":
        created = await _commit_partners(db, caller, good)
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
                                  price_list_id=target)


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
