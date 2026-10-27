"""The shared half of every `/export` endpoint (FS-030).

`filters_of(list_endpoint)` builds a dependency whose query parameters are the list
endpoint's own, minus paging, read from its signature. So an export takes every
filter its list takes, under the same name and validation, by construction: a
filter added to the list later appears on the export without anyone remembering
(Build-Plan 9.3 rule 2).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, Literal

from fastapi import Query, Response
from pydantic import BaseModel

from api.schemas.auth import ErrorResponse
from api.services import exports, report_pdf

# paging, and the dependencies the export resolves for itself
_NOT_FILTERS = frozenset({"limit", "cursor", "include_total", "db", "caller", "claims"})

_BINARY: dict[str, Any] = {"schema": {"type": "string", "format": "binary"}}

XLSX_RESPONSE: dict[int | str, dict[str, Any]] = {200: {
    "description": "The workbook, as an attachment.",
    "content": {exports.XLSX_TYPE: _BINARY}}}

# FS-077: every list export as Excel or CSV
EXPORT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"description": "The file, as an attachment: Excel (`format=xlsx`, the default) or CSV.",
          "content": {exports.XLSX_TYPE: _BINARY, exports.CSV_TYPE: _BINARY}},
    422: {"model": ErrorResponse, "description": "`format_not_available` (`pdf` on a list); "
                                                 "`export_too_large`; a bad filter."}}

# FS-077: a report export also as PDF (HTML where the box has no PDF renderer)
REPORT_EXPORT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"description": "The file, as an attachment: Excel, CSV or PDF.",
          "content": {exports.XLSX_TYPE: _BINARY, exports.CSV_TYPE: _BINARY,
                      exports.PDF_TYPE: _BINARY, "text/html": _BINARY}},
    422: {"model": ErrorResponse,
          "description": "`export_too_large`: a PDF holds 1,000 rows at most; a bad filter."},
    503: {"model": ErrorResponse, "description": "`busy`: two PDFs are being made, try again in a "
                                                 "moment; `pdf_unavailable`."}}

ExportFormat = Annotated[Literal["xlsx", "csv", "pdf"], Query(
    alias="format", description="`xlsx` (default) or `csv`. `pdf` only on reports; on a list it "
                                "answers `422 format_not_available`. Lower case.")]

PDF_MAX_ROWS = 1000
_PDF_TOO_LARGE = "A PDF holds at most 1,000 rows. Use Excel or CSV for more, or narrow the filters."


def file_response(body: bytes, media_type: str, stem: str, ext: str) -> Response:
    """An export as an attachment, never cached and never sniffed (FS-077 EC-25)."""
    return Response(content=body, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{exports.filename(stem, ext=ext)}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def filters_of(endpoint: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """A dependency returning the list's filters as keyword arguments."""
    sig = inspect.signature(endpoint, eval_str=True)
    params = [p for name, p in sig.parameters.items() if name not in _NOT_FILTERS]
    # the export's own `format` would collide with a list filter of that name
    # (FS-077 plan review Q2)
    if any(p.name in ("format", "fmt") for p in params):
        raise TypeError(f"{endpoint.__name__} has a `format` filter; rename it")

    def dep(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    dep.__signature__ = sig.replace(parameters=params,  # type: ignore[attr-defined]
                                    return_annotation=dict)
    return dep


async def export(endpoint: Callable[..., Awaitable[Any]], *, stem: str, title: str,
                 columns: Sequence[exports.Column], user_id: str, filters: dict[str, Any],
                 fmt: str = "xlsx", allow_pdf: bool = False, **deps: Any) -> Response:
    """Drain the list endpoint itself, called page by page with the filters and the
    caller's own `db` and `caller`, then answer with the file. The workbook is built in
    a thread, as the PIMS sheet is. `pdf` only where `allow_pdf` (the subsidy reports),
    refused on a list before any row is read (FS-077 EC-14)."""
    if fmt == "pdf":
        if not allow_pdf:
            raise exports.FormatNotAvailableError("A list exports to Excel or CSV, not PDF.")
        report_pdf.check_ready()
    accepted = inspect.signature(endpoint).parameters

    async def fetch(cursor: str | None) -> tuple[Sequence[BaseModel], str | None]:
        paging = {"limit": exports.PAGE, "cursor": cursor, "include_total": False}
        given = {**deps, **paging}
        kwargs = {**filters, **{k: v for k, v in given.items() if k in accepted}}
        result = await endpoint(**kwargs)
        return result.data, result.meta.next_cursor

    if fmt == "pdf":
        rows = await exports.drain(fetch, cap=PDF_MAX_ROWS, message=_PDF_TOO_LARGE)
        db = deps.get("db")
        made_by = await report_pdf.caller_name(db) if db is not None else None
        page = report_pdf.Page(title=title, columns=columns, rows=rows, total=None, notes=(),
                               filter_line=report_pdf.list_filter_line(filters))
        body, media, ext = await report_pdf.render(report_pdf.html(page, made_by))
        exports.log_export(user_id, stem, filters, len(rows), fmt=fmt)
        return file_response(body, media, stem, ext)
    rows = await exports.drain(fetch)
    if fmt == "csv":
        body = await asyncio.to_thread(exports.csv_bytes, columns, rows)
        exports.log_export(user_id, stem, filters, len(rows), fmt=fmt)
        return file_response(body, exports.CSV_TYPE, stem, "csv")
    data = await asyncio.to_thread(exports.workbook, title, columns, rows)
    exports.log_export(user_id, stem, filters, len(rows), fmt=fmt)
    return file_response(data, exports.XLSX_TYPE, stem, "xlsx")
