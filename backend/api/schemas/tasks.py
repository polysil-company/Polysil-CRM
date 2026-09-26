"""Tasks, the planner, meeting types and meeting minutes (FS-014)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field

from api.domain import tasks as domain
from api.schemas.leads import UUID_RE, PageMeta, UserRef

TaskType = Literal["call", "visit", "meeting", "followup", "other"]
TaskStatus = Literal["open", "done", "cancelled"]
_Id = Annotated[str, Field(pattern=UUID_RE)]
_Text = Annotated[str, Field(min_length=1, max_length=domain.TEXT_MAX)]


def _date_alone(v: object) -> object:
    # pydantic reads "2026-10-02" as a naive midnight datetime, which then fails
    # the timezone rule; a bare date means 18:00 IST (rule 8)
    if isinstance(v, str) and len(v) == 10:
        try:
            return dt.date.fromisoformat(v)
        except ValueError:
            return v
    return v


DueAt = Annotated[dt.datetime | dt.date, BeforeValidator(_date_alone)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=domain.TITLE_MAX)]
    task_type: TaskType
    due_at: DueAt = Field(
        description="With a timezone, for example 2026-10-02T10:30:00+05:30. A date alone "
                    "means 18:00 IST. Past times are allowed, for logging what was done.")
    assigned_to: _Id | None = Field(
        default=None, description="Defaults to you. Offer only people from GET /tasks/assignees.")
    lead_id: _Id | None = None
    partner_id: _Id | None = Field(default=None, description="A dealer or distributor.")
    sales_order_id: _Id | None = None
    meeting_type_id: _Id | None = Field(
        default=None, description="Required for a meeting on a lead; refused otherwise. "
                                  "From GET /lookups/meeting-types.")
    notes: Annotated[str | None, Field(default=None, max_length=domain.TEXT_MAX)]


class TaskPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[str | None, Field(default=None, min_length=1, max_length=domain.TITLE_MAX)]
    due_at: DueAt | None = None
    notes: Annotated[str | None, Field(default=None, max_length=domain.TEXT_MAX)]
    assigned_to: _Id | None = Field(default=None, description="Reassign. The new person must "
                                                              "be one you may assign to.")
    expected_status: TaskStatus | None = None


class TaskComplete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    outcome: _Text = Field(description="What happened. Required.")
    gift_shown: bool | None = Field(default=None, description="Meetings only.")


class TaskCancel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    reason: _Text


class _Link(BaseModel):
    id: str
    hidden: bool = Field(default=False, description="True when you can no longer see it: "
                                                    "show 'not visible'. The other fields "
                                                    "are then null.")


class LeadLink(_Link):
    inquiry_no: str | None = None
    farmer_name: str | None = None


class PartnerLink(_Link):
    name: str | None = None
    partner_type: str | None = Field(default=None, description="dealer or distributor.")


class OrderLink(_Link):
    order_no: str | None = Field(default=None, description="Null on a draft.")


class MeetingTypeRef(BaseModel):
    id: str
    code: str
    name: str


class Task(BaseModel):
    id: str
    title: str
    task_type: TaskType
    status: TaskStatus
    overdue: bool = Field(description="Open and past its due time. Computed; never compute it "
                                      "on the screen.")
    due_at: str
    assigned_to: UserRef | None
    assigned_by: UserRef | None
    lead: LeadLink | None
    partner: PartnerLink | None
    sales_order: OrderLink | None
    meeting_type: MeetingTypeRef | None
    minutes_id: str | None = Field(description="Set when this is an action item of meeting "
                                               "minutes.")
    notes: str | None
    outcome: str | None
    gift_shown: bool | None
    cancel_reason: str | None
    completed_at: str | None
    completed_by: UserRef | None
    created_at: str
    updated_at: str


class TaskPage(BaseModel):
    data: list[Task]
    meta: PageMeta


class PlannerDay(BaseModel):
    date: str
    user: UserRef | None
    due: list[Task] = Field(description="Due that day, by time.")
    overdue: list[Task] = Field(description="Open and due before that day, up to 90 days "
                                            "back. Empty for a future date.")


class TeamRow(BaseModel):
    user: UserRef
    org_unit_id: str | None
    due_today: int
    done_today: int
    overdue: int


class TeamPage(BaseModel):
    data: list[TeamRow]
    meta: PageMeta


class ActionItemIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=domain.TITLE_MAX)]
    due_at: DueAt
    assigned_to: _Id | None = None
    task_type: Literal["call", "visit", "followup", "other"] = "followup"


class MinutesCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    lead_id: _Id | None = None
    partner_id: _Id | None = None
    task_id: _Id | None = Field(default=None, description="The meeting these minutes record; "
                                                          "completed if still open.")
    held_at: AwareDatetime = Field(description="With a timezone, for example "
                                               "2026-10-02T15:00:00+05:30.")
    attendees: Annotated[list[Annotated[str, Field(max_length=domain.ATTENDEE_MAX)]],
                         Field(default_factory=list, max_length=domain.ATTENDEES_MAX)]
    notes: _Text
    action_items: Annotated[list[ActionItemIn], Field(default_factory=list, max_length=50)]


class Minutes(BaseModel):
    id: str
    lead: LeadLink | None
    partner: PartnerLink | None
    task_id: str | None
    held_at: str
    attendees: list[str]
    notes: str
    created_by: UserRef | None
    created_at: str
    action_items: list[Task] = Field(description="Each action item's task, as it stands now.")
