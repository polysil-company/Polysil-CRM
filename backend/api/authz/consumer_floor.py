"""The consumer floor (FS-044): one restrictive policy on every RLS table that a
consumer's claim can never pass.

A consumer (a farmer signed in to the portal) has no role and no partner, so every
policy written as "signed in" or "not a partner" would admit one. The portal reads
through SECURITY DEFINER functions, which run as the owner and skip RLS, so the
floor costs the portal nothing. Two tables keep the consumer's own rows: app_user
(`/auth/me`) and idempotency_record (the portal's one write takes a key).

Migration 052 applies it to every table with RLS on. A migration that later turns
RLS on for a new table adds `policy_sql(table)` too; test_consumer_floor asserts
every RLS table carries it.
"""

from __future__ import annotations

FUNCTION = "app_is_consumer"
_DENY = f"(SELECT {FUNCTION}())"
# tables where a consumer keeps its own rows, and the column that names the owner
OWN_ROWS: dict[str, str] = {"app_user": "id", "idempotency_record": "user_id"}


def name(table: str) -> str:
    return f"{table}_res_not_consumer"


def predicate(table: str) -> str:
    own = OWN_ROWS.get(table)
    if own is None:
        return f"NOT {_DENY}"
    return f"(NOT {_DENY} OR {own} = (SELECT app_current_user_id()))"


def policy_sql(table: str) -> str:
    p = predicate(table)
    return (f"CREATE POLICY {name(table)} ON {table} AS RESTRICTIVE FOR ALL "
            f"USING ({p}) WITH CHECK ({p})")
