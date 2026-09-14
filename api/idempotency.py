"""The idempotency helper. Every mutation runs through it (rule 5, AC-IDEM 1-13).

FS-003 section 4. A mutation reserves a record, does its work in a savepoint, and
stores its response, so a retry with the same key replays the stored answer and a
retry with a different payload under the same key is refused.

The record is reserved by the route, *after* authentication, require() and body
validation, so a 401, a missing-key 400, a require() 403 and a schema 422 store
nothing and re-execute on a retry, each being deterministic (plan review B-5). Every
4xx the handler itself raises is stored: a client cannot retry past a business rule.
A 5xx stores nothing, so a genuine retry genuinely retries.

Concurrency (AC-IDEM-5): the reserve is INSERT ... ON CONFLICT DO NOTHING, which
blocks on a concurrent winner's uncommitted row and returns no row once it commits,
so the loser reads a `done` record rather than racing it. It never raises, so the
transaction is never aborted. Executed against 16.14 through PgBouncer.

The store is an UPDATE of the reserved row, which needs the UPDATE grant and policy
migration 006 adds; 005 wrote neither and the step was 42501 (plan review B-1).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import IdempotencyConflictError

# A handler returns its HTTP status and the response body (the full envelope the
# client receives), or raises an ApiError.
Work = Callable[[], Awaitable[tuple[int, dict[str, Any]]]]


@dataclass(frozen=True)
class Outcome:
    """What the route turns into a response. `replayed` is a stored answer returned
    without running the work again."""

    status_code: int
    body: dict[str, Any]
    replayed: bool = False


def payload_digest(payload: Any) -> str:
    """A stable hash of the request payload, for the same-key-different-body check.
    Bytes are hashed as given; anything else is canonical JSON so key order and
    spacing do not change the digest."""
    if isinstance(payload, bytes | bytearray):
        raw = bytes(payload)
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


_RESERVE = text(
    "INSERT INTO idempotency_record (key, user_id, route, request_hash, state) "
    "VALUES (:k, CAST(:u AS uuid), :r, :h, 'in_progress') "
    "ON CONFLICT (key, user_id, route) DO NOTHING RETURNING id"
)
_PRIOR = text(
    "SELECT request_hash, state, status_code, response_json FROM idempotency_record "
    "WHERE key = :k AND user_id = CAST(:u AS uuid) AND route = :r"
)
_STORE = text(
    "UPDATE idempotency_record SET state = 'done', status_code = :s, "
    "response_json = CAST(:b AS jsonb), completed_at = now() WHERE id = :id"
)


async def _store(db: AsyncSession, record_id: Any, status_code: int,
                 body: dict[str, Any]) -> None:
    await db.execute(_STORE, {"s": status_code, "b": json.dumps(body), "id": record_id})


async def run_idempotent(db: AsyncSession, *, key: str, user_id: str, route: str,
                         payload_hash: str, work: Work) -> Outcome:
    """Reserve the key, run the work once, store and return its response.

    `route` is the mutation's identity, method and path template, so the same key
    on two different endpoints is two records (round 4 recommendation). The caller
    has already passed authentication, require() and validation before this runs.
    """
    reserved = (await db.execute(
        _RESERVE, {"k": key, "u": user_id, "r": route, "h": payload_hash}
    )).scalar_one_or_none()

    if reserved is None:
        # Someone else owns the key. ON CONFLICT DO NOTHING blocked until they
        # committed, so the row is `done` (a winner that rolled back released the
        # key and we would have won it instead).
        prior = (await db.execute(_PRIOR, {"k": key, "u": user_id, "r": route})).one()
        if prior.request_hash != payload_hash:
            raise IdempotencyConflictError()
        body = prior.response_json
        if isinstance(body, str):  # asyncpg hands jsonb back as text
            body = json.loads(body)
        return Outcome(prior.status_code, body, replayed=True)

    # We won it. The work runs in a savepoint so a business 4xx rolls its writes
    # back while the record we store to survives the request's commit.
    savepoint = await db.begin_nested()
    try:
        status_code, body = await work()
    except Exception as exc:
        # The savepoint is always closed, so the session stays usable and a 42501
        # that aborted the sub-transaction is recovered here rather than poisoning
        # the connection.
        await savepoint.rollback()
        status = getattr(exc, "status_code", 500)
        if not isinstance(status, int) or status >= 500:
            # A 5xx or an unexpected error: let it propagate. get_db rolls the whole
            # transaction back, the reserved row included, so a retry is a first
            # attempt (AC-IDEM-6, EC-6: a 42501 lands here). Nothing is stored.
            raise
        # A business 4xx: its writes are gone with the savepoint, but the record we
        # store to is outside it and survives the request's commit (AC-IDEM-7).
        envelope = exc.envelope() if hasattr(exc, "envelope") else {
            "error": {"code": "error", "message": str(exc)}}
        await _store(db, reserved, status, envelope)
        return Outcome(status, envelope)
    else:
        await savepoint.commit()
        await _store(db, reserved, status_code, body)
        return Outcome(status_code, body)
