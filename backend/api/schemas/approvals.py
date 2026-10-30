"""The approval chain as the API shows it, on an order (FS-011) and on a quotation
(FS-013). Its own module so both document schemas can carry it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.leads import UserRef

ApprovalStatus = Literal["pending", "approved", "rejected", "cancelled"]
Decision = Literal["approve", "reject"]


class ApprovalStep(BaseModel):
    id: str
    seq: int = Field(description="1 is decided first.")
    role: str = Field(description="The role code the step waits on.")
    decided_role: str | None = Field(description="Set when a higher manager decided this "
                                                 "step in place of its own role.")
    decision: Decision | None = Field(description="Null while undecided.")
    by: UserRef | None = Field(description="Null for a dealer, always.")
    remark: str | None = Field(description="Null for a dealer, always.")
    decided_at: str | None
    stalled: bool = Field(
        default=False,
        description="True on the step waiting now when nobody of its own role can decide it "
                    "(none covers the document, or the only one raised it). A higher manager "
                    "decides it instead and sees it in their inbox. Show \"No <role> to decide; "
                    "with the next manager up\" rather than \"Waiting on <role>\". "
                    "Always false for a dealer.")


class Approval(BaseModel):
    request_id: str
    status: ApprovalStatus = Field(
        description="cancelled when the document was cancelled, or a quotation edited, "
                    "while pending.")
    steps: list[ApprovalStep]
    request_remark: str | None = Field(
        default=None, description="Why the approval was asked for (a quotation discount). "
                                  "Null for a dealer, always.")
