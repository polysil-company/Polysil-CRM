"""Names of the people and partners on documents the caller can see (RBAC.md 6.2,
GAP-060).

A list joins `app_user` and `channel_partner` under the caller's own policies, so
a name the caller's `users` or `partners` scope does not reach comes back null
while its id is set: a dealer who created a lead, an administrator at head office.
`people_names()` and `partner_names()` (migration 014) answer for exactly those
ids, and only when the person or partner is on a document the caller can see.
One round trip each per page, and none when every name resolved.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.leads import PartnerRef, UserRef


@dataclass
class Names:
    users: dict[str, str] = field(default_factory=dict)
    partners: dict[str, tuple[str, str]] = field(default_factory=dict)

    def user(self, user_id: Any, joined: str | None) -> UserRef | None:
        """The ref for an id: the joined name when the caller's scope reached it,
        else the resolved one. None only when there is no id, or the person is on
        nothing the caller can see."""
        if not user_id:
            return None
        name = joined or self.users.get(str(user_id))
        return UserRef(id=str(user_id), full_name=name) if name else None

    def partner(self, partner_id: Any, joined: str | None,
                joined_type: str | None) -> PartnerRef | None:
        if not partner_id:
            return None
        if joined:
            return PartnerRef(id=str(partner_id), name=joined, partner_type=str(joined_type or ""))
        found = self.partners.get(str(partner_id))
        return (PartnerRef(id=str(partner_id), name=found[0], partner_type=found[1])
                if found else None)


async def resolve(db: AsyncSession, rows: Sequence[Any],
                  users: Iterable[tuple[str, str]] = (),
                  partners: Iterable[tuple[str, str]] = ()) -> Names:
    """`users` and `partners` are (id attribute, joined-name attribute) pairs on the
    rows. Only the ids whose joined name is null are looked up."""
    missing_users = {str(getattr(r, i)) for r in rows for i, n in users
                     if getattr(r, i) and not getattr(r, n)}
    missing_partners = {str(getattr(r, i)) for r in rows for i, n in partners
                        if getattr(r, i) and not getattr(r, n)}
    return await resolve_ids(db, missing_users, missing_partners)


async def resolve_ids(db: AsyncSession, user_ids: Iterable[str] = (),
                      partner_ids: Iterable[str] = ()) -> Names:
    names = Names()
    u = sorted(set(user_ids))
    p = sorted(set(partner_ids))
    if u:
        names.users = {str(r.id): r.full_name for r in (await db.execute(text(
            "SELECT id, full_name FROM people_names(CAST(:ids AS uuid[]))"), {"ids": u})).all()}
    if p:
        names.partners = {str(r.id): (r.name, r.partner_type) for r in (await db.execute(text(
            "SELECT id, name, partner_type FROM partner_names(CAST(:ids AS uuid[]))"),
            {"ids": p})).all()}
    return names
