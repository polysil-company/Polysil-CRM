"""Shapes for /notifications (FS-018), matching the frontend's proposed contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.leads import UUID_RE, UserRef


class ResourceRef(BaseModel):
    type: str = Field(description="lead, task, sales_order, quotation or complaint.")
    id: str
    label: str = Field(description="The record's number or title, for the link text.")


class Notification(BaseModel):
    id: str
    kind: str = Field(description="lead_assigned, task_assigned, lead_note, approval_requested, "
                      "complaint_to_check, complaint_to_qc, complaint_assigned, order_approved, "
                      "order_returned, discount_approved, discount_returned, complaint_returned, "
                      "complaint_qc_approved, complaint_qc_rejected. Show an unknown kind "
                      "generically.")
    title: str
    body: str | None
    actor: UserRef | None = Field(description="Who caused it. Null for a dealer on a decision: "
                                  "a dealer is never told who decided.")
    resource: ResourceRef | None
    created_at: str
    read_at: str | None = Field(description="Null while unread.")


class NotificationMeta(BaseModel):
    unread_count: int = Field(description="All your unread notifications, not only this page.")
    next_cursor: str | None


class NotificationPage(BaseModel):
    data: list[Notification]
    meta: NotificationMeta


class MarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[Annotated[str, Field(pattern=UUID_RE)]] | None,
                   Field(default=None, min_length=1, max_length=200,
                         description="Mark these read. Ids not yours, or already read, "
                         "are ignored.")]
    all: Literal[True] | None = Field(default=None, description="Mark everything read.")

    @model_validator(mode="after")
    def _one_of(self) -> MarkRead:
        if (self.ids is None) == (self.all is None):
            raise ValueError("send ids or all, not both")
        return self


class UnreadCount(BaseModel):
    unread_count: int
