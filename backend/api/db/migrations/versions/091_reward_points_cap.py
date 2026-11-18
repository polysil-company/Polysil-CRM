"""091: an order's reward points never take a balance past int4 (FS-090).

`reward_earn_order()` cast `floor(value / per_amount) * points` to int. FS-090
raised a document to ₹1,000 crore, and at 1 point per ₹1 that is 10,000,000,000
points: `integer out of range` inside the delivery trigger, so the order could not
be marked delivered. A rule of 1,000,000 points per ₹1 hit it on any order already.

The earning now takes at most the room left under 2,147,483,647 in the holder's
balance, so `reward_balance()`'s `sum(points)::int` cannot overflow from earnings
either. Capping each row alone would not do that: two capped rows overflow the sum.
The cap is an assumption (GAP-597, client question 44.2).

Patched by its live text, as 090 does; nothing has changed it since 036.

Revision ID: 091_reward_points_cap
Revises: 090_industrial_order_ladder
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "091_reward_points_cap"
down_revision: str | None = "090_industrial_order_ladder"
branch_labels = None
depends_on = None

EARN = "reward_earn_order(uuid, date)"
OLD = "v_points := (floor(v_value / r.per_amount) * r.points)::int;"
NEW = """v_points := least(floor(v_value / r.per_amount) * r.points,
                          2147483647 - (SELECT coalesce(sum(x.points), 0) FROM reward_ledger x
                                         WHERE CASE r.holder
                                               WHEN 'partner' THEN x.holder_type = 'partner'
                                                                   AND x.partner_id = o.partner_id
                                               ELSE x.holder_type = 'user'
                                                    AND x.user_id = o.owner_user_id END))::int;"""


def _swap(old: str, new: str) -> None:
    body = str(op.get_bind().execute(
        text(f"SELECT pg_get_functiondef('{EARN}'::regprocedure)")).scalar_one())
    if body.count(old) != 1:
        raise RuntimeError(f"091: {EARN} anchor {old[:40]!r} found {body.count(old)} times")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    _swap(OLD, NEW)


def downgrade() -> None:
    _swap(NEW, OLD)
