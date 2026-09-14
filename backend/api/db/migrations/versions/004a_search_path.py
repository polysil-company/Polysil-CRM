"""004a search_path on the two tree functions

Executed on 16.14 during the code review of 004: with a schema shadowing
channel_partner first on the search path, an illegal sub_dealer under a
distributor was accepted, because the type-order trigger's SELECT resolved to
the empty shadow table, got NULL, and took the "missing parent is the FK's
problem" branch while the real FK was satisfied. Worse, a LEGAL insert under the
same shadowed path got one closure row instead of two: closure_maintain()'s
recursive walk joined the shadow table, found no parent, and wrote only the
self row. A partner invisible to its own distributor, no error anywhere. That
is the FS-001 9.8 X-6 failure mode by another route.

Every other function this project creates carries SET search_path = public.
These two did not. closure_maintain() is 002's and has run on other machines,
so this is forward-only (ISS-046). channel_partner_type_order() is 004's and
could have been amended in place; it is fixed here too so the fix is in one
place.

CREATE OR REPLACE keeps ownership and privileges, so the REVOKE FROM PUBLIC that
003 and 004 already applied survives. Asserted at the end regardless.

Revision ID: 004a_search_path
Revises: 004_channel_tree
Created: during development
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "004a_search_path"
down_revision: str | None = "004_channel_tree"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = ("closure_maintain()", "channel_partner_type_order()")


def _set_search_path(fn: str, on: bool) -> None:
    # Re-emit the function with its current body and a changed header rather than
    # duplicating two hundred lines of plpgsql here. pg_get_functiondef returns the
    # full CREATE OR REPLACE statement; the header is the part before AS $fn$.
    conn = op.get_bind()
    src = conn.execute(
        text("SELECT pg_get_functiondef(CAST(:f AS regprocedure))"), {"f": fn}
    ).scalar_one()
    head, sep, body = src.partition("\nAS ")
    if not sep:
        raise RuntimeError(f"unexpected pg_get_functiondef shape for {fn}")
    head = re.sub(r"\s+SET search_path TO [^\n]+", "", head)
    if on:
        head = head + "\n SET search_path TO public"
    op.execute(head + sep + body)


def upgrade() -> None:
    for fn in FUNCTIONS:
        _set_search_path(fn, on=True)
    op.execute(
        """
        DO $$
        DECLARE v_public int; v_unset int;
        BEGIN
            SELECT count(*) INTO v_public
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
             WHERE n.nspname = 'public' AND d.objid IS NULL
               AND has_function_privilege('public', p.oid, 'EXECUTE');
            IF v_public > 0 THEN
                RAISE EXCEPTION '% functions in public are executable by PUBLIC', v_public;
            END IF;
            SELECT count(*) INTO v_unset
              FROM pg_proc
             WHERE proname IN ('closure_maintain', 'channel_partner_type_order')
               AND NOT coalesce(proconfig, '{}') @> ARRAY['search_path=public'];
            IF v_unset > 0 THEN
                RAISE EXCEPTION '% tree functions still have no search_path', v_unset;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    for fn in FUNCTIONS:
        _set_search_path(fn, on=False)
