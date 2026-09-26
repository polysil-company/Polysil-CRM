"""An approval chain as the API shows it, for any document the engine approves
(FS-011 orders, FS-013 quotations). A dealer sees each step's role, outcome and
time, never who decided or why."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.approvals import Approval, ApprovalStep
from api.services import people


def _iso(v: Any) -> str | None:
    return None if v is None else v.isoformat()


async def load(db: AsyncSession, doc_type: str, entity_id: str, portal: bool,
               request_id: str | None = None) -> tuple[Approval | None, Any]:
    """The named request of the document, or its latest. The second value is the raw
    request and step rows, for callers that read more than the view."""
    req = (await db.execute(text(
        "SELECT id, status::text AS status, remark FROM approval_request "
        "WHERE doc_type = :d AND entity_id = CAST(:e AS uuid) "
        "AND (CAST(:r AS uuid) IS NULL OR id = CAST(:r AS uuid)) "
        "ORDER BY created_at DESC, id DESC LIMIT 1"),
        {"d": doc_type, "e": entity_id, "r": request_id})).one_or_none()
    if req is None:
        return None, None
    steps = (await db.execute(text(
        "SELECT s.id, s.seq, r.code::text AS role, dr.code::text AS decided_role, "
        "s.decision::text AS decision, s.approver_user_id, u.full_name, s.remark, s.decided_at "
        "FROM approval_step s JOIN role r ON r.id = s.approver_role_id "
        "LEFT JOIN role dr ON dr.id = s.decided_role_id "
        "LEFT JOIN app_user u ON u.id = s.approver_user_id "
        "WHERE s.request_id = CAST(:r AS uuid) ORDER BY s.seq"), {"r": str(req.id)})).all()
    names = (people.Names() if portal
             else await people.resolve(db, steps, [("approver_user_id", "full_name")]))
    out = []
    for s in steps:
        out.append(ApprovalStep(
            id=str(s.id), seq=s.seq, role=s.role,
            decided_role=s.decided_role if s.decided_role and s.decided_role != s.role else None,
            decision=s.decision, by=None if portal else names.user(s.approver_user_id, s.full_name),
            remark=None if portal else s.remark, decided_at=_iso(s.decided_at)))
    return Approval(request_id=str(req.id), status=req.status, steps=out,
                    request_remark=None if portal else req.remark), (req, steps)
