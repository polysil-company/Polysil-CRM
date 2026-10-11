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
from typing import Any

from fastapi import Response
from pydantic import BaseModel

from api.services import exports

# paging, and the dependencies the export resolves for itself
_NOT_FILTERS = frozenset({"limit", "cursor", "include_total", "db", "caller", "claims"})

XLSX_RESPONSE: dict[int | str, dict[str, Any]] = {200: {
    "description": "The workbook, as an attachment.",
    "content": {exports.XLSX_TYPE: {"schema": {"type": "string", "format": "binary"}}}}}


def filters_of(endpoint: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """A dependency returning the list's filters as keyword arguments."""
    sig = inspect.signature(endpoint, eval_str=True)
    params = [p for name, p in sig.parameters.items() if name not in _NOT_FILTERS]

    def dep(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    dep.__signature__ = sig.replace(parameters=params,  # type: ignore[attr-defined]
                                    return_annotation=dict)
    return dep


async def export(endpoint: Callable[..., Awaitable[Any]], *, stem: str, title: str,
                 columns: Sequence[exports.Column], user_id: str, filters: dict[str, Any],
                 **deps: Any) -> Response:
    """Drain the list endpoint itself, called page by page with the filters and the
    caller's own `db` and `caller`, then answer with the workbook. The workbook is
    built in a thread, as the PIMS sheet is."""
    accepted = inspect.signature(endpoint).parameters

    async def fetch(cursor: str | None) -> tuple[Sequence[BaseModel], str | None]:
        paging = {"limit": exports.PAGE, "cursor": cursor, "include_total": False}
        given = {**deps, **paging}
        kwargs = {**filters, **{k: v for k, v in given.items() if k in accepted}}
        result = await endpoint(**kwargs)
        return result.data, result.meta.next_cursor

    rows = await exports.drain(fetch)
    data = await asyncio.to_thread(exports.workbook, title, columns, rows)
    exports.log_export(user_id, stem, filters, len(rows))
    return Response(content=data, media_type=exports.XLSX_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{exports.filename(stem)}"'})
