"""Field tracking (FS-021): duty, location batches, visits, the team map, routes."""

# ruff: noqa: E501  (field descriptions are the generated API doc)

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta, UserRef

_Id = Annotated[str, Field(pattern=UUID_RE)]
Lat = Annotated[float, Field(ge=-90, le=90, description="Degrees, WGS84.")]
Lng = Annotated[float, Field(ge=-180, le=180, description="Degrees, WGS84.")]
Accuracy = Annotated[float | None, Field(default=None, ge=0, le=100_000,
                                         description="The fix's accuracy radius in metres.")]
DeviceId = Annotated[str, Field(min_length=8, max_length=100,
                                description="The app install's own id. The same for every request from one install.")]
EndReason = Literal["user", "auto", "consent_withdrawn", "deactivated"]
Outcome = Literal["met", "not_available", "follow_up", "other"]
RejectReason = Literal["off_duty", "future", "too_old", "bad_coordinates", "unknown_duty", "id_in_use",
                       "consent_withdrawn"]


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Position(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None = None


# ── config, consent, policy ─────────────────────────────────────────────────

class WorkingHours(BaseModel):
    start: str = Field(description="HH:MM, IST.")
    end: str = Field(description="HH:MM, IST. Exclusive.")
    days: list[int] = Field(description="ISO weekdays: 1 is Monday, 7 is Sunday.")
    timezone: str = "Asia/Kolkata"


class ConsentState(BaseModel):
    required_version: str = Field(description="The version a duty start needs.")
    accepted_version: str | None = Field(description="The newest version this user accepted and did not withdraw. Null when none.")
    text: str = Field(description="What the consent screen shows.")


class OnDuty(BaseModel):
    id: str
    started_at: str


class TrackingConfig(BaseModel):
    tracking_allowed: bool = Field(description="False: this role does not track. Hide the duty toggle.")
    consent: ConsentState
    interval_seconds: int = Field(description="The background plugin's time filter.")
    distance_filter_m: int = Field(description="The background plugin's distance filter.")
    working_hours: WorkingHours
    max_batch_points: int = Field(description="The most points one batch may carry.")
    visit_photo_required: bool = Field(description="True: check-out needs at least one photo.")
    on_duty: OnDuty | None = Field(description="The open duty session, or null.")


class ConsentIn(_In):
    version: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,20}$", description="The version shown.")]
    accepted: bool = Field(description="False withdraws consent and ends any open duty.")


class Consent(BaseModel):
    id: str
    version: str
    accepted: bool
    at: str


class Policy(BaseModel):
    effective_from: str
    interval_seconds: int
    distance_filter_m: int
    working_hours: WorkingHours
    retention_days: int = Field(description="Location points older than this are deleted nightly.")
    visit_photo_required: bool
    consent_version: str
    consent_text: str


class PolicyIn(_In):
    effective_from: AwareDatetime = Field(description="When this version takes over. Never in the past.")
    interval_seconds: Annotated[int, Field(ge=15, le=3600)]
    distance_filter_m: Annotated[int, Field(ge=0, le=5000)]
    work_start: dt.time = Field(description="HH:MM, IST.")
    work_end: dt.time = Field(description="HH:MM, IST. After work_start.")
    work_days: Annotated[list[Annotated[int, Field(ge=1, le=7)]], Field(min_length=1, max_length=7,
                                                                       description="ISO weekdays, 1 is Monday.")]
    retention_days: Annotated[int, Field(ge=7, le=3650)]
    visit_photo_required: bool
    consent_version: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,20}$",
                                          description="A new version asks everyone again at their next duty start.")]
    consent_text: Annotated[str, Field(min_length=1, max_length=10_000)]


# ── duty ────────────────────────────────────────────────────────────────────

class DutyStart(_In):
    id: _Id = Field(description="Made on the phone, so a retry never opens a second session.")
    device_id: DeviceId
    at: AwareDatetime
    sent_at: AwareDatetime | None = Field(default=None, description="The phone's clock when sending. Send it: a phone clock more than 5 minutes off is then corrected.")
    lat: Lat
    lng: Lng
    accuracy_m: Accuracy


class DutyEnd(_In):
    id: _Id = Field(description="The session to end.")
    at: AwareDatetime
    sent_at: AwareDatetime | None = Field(default=None, description="The phone's clock when sending. Send it: a phone clock more than 5 minutes off is then corrected.")
    lat: Lat | None = None
    lng: Lng | None = None
    accuracy_m: Accuracy


class Duty(BaseModel):
    id: str
    started_at: str
    ended_at: str | None
    end_reason: EndReason | None = Field(description="user, auto (idle after hours, or 14 hours), consent_withdrawn or deactivated.")
    outside_hours: bool = Field(description="Started outside the policy's working hours.")


# ── points ──────────────────────────────────────────────────────────────────

class PointIn(_In):
    id: _Id = Field(description="Made on the phone when the fix is taken.")
    duty_id: _Id = Field(description="The open duty's id, as the server answered it.")
    recorded_at: AwareDatetime = Field(description="When the fix was taken, by the phone's clock.")
    lat: float = Field(description="Degrees. Out of range is rejected per point, not per batch.")
    lng: float
    accuracy_m: Accuracy
    speed_mps: Annotated[float | None, Field(default=None, ge=0, le=1000)]
    heading: Annotated[float | None, Field(default=None, ge=0, le=360)]
    altitude_m: Annotated[float | None, Field(default=None, ge=-1000, le=10_000)]
    battery_pct: Annotated[int | None, Field(default=None, ge=0, le=100)]
    is_mock: bool = Field(default=False, description="The plugin's `simulated` flag.")


class BatchIn(_In):
    device_id: DeviceId
    sent_at: AwareDatetime = Field(description="The phone's clock when sending. Corrects a phone clock that is off.")
    points: Annotated[list[PointIn], Field(min_length=1, description="Oldest first.")]


class Rejected(BaseModel):
    id: str
    reason: RejectReason


class BatchDuty(BaseModel):
    id: str
    ended_at: str | None
    end_reason: EndReason | None


class BatchResult(BaseModel):
    accepted: int
    duplicates: int = Field(description="Points already stored. Delete them on the phone too.")
    rejected: list[Rejected] = Field(description="Never accepted later. Delete them on the phone.")
    duty: BatchDuty | None = Field(description="The duty of the batch's newest point. When ended_at is set, stop tracking.")


# ── visits ──────────────────────────────────────────────────────────────────

class VisitIn(_In):
    id: _Id = Field(description="Made on the phone.")
    lead_id: _Id | None = None
    partner_id: _Id | None = Field(default=None, description="A dealer. Not with lead_id.")
    task_id: _Id | None = Field(default=None, description="A task assigned to you, optional.")
    place_name: Annotated[str | None, Field(default=None, min_length=1, max_length=200,
                                            description="Required when there is no lead or dealer.")]
    at: AwareDatetime
    sent_at: AwareDatetime | None = Field(default=None, description="The phone's clock when sending. Send it: a phone clock more than 5 minutes off is then corrected.")
    lat: Lat
    lng: Lng
    accuracy_m: Accuracy


class CheckOut(_In):
    at: AwareDatetime
    sent_at: AwareDatetime | None = Field(default=None, description="The phone's clock when sending. Send it: a phone clock more than 5 minutes off is then corrected.")
    lat: Lat
    lng: Lng
    accuracy_m: Accuracy
    outcome: Outcome
    note: Annotated[str | None, Field(default=None, max_length=2000)]


class DocRef(BaseModel):
    id: str
    label: str


class Visit(BaseModel):
    id: str
    user: UserRef
    lead: DocRef | None
    partner: DocRef | None
    task_id: str | None
    place_name: str | None
    checkin_at: str
    checkin: Position
    checkout_at: str | None
    checkout: Position | None
    duration_minutes: int | None
    outcome: Outcome | None
    note: str | None
    auto_closed: bool = Field(description="Closed by the server 12 hours after check-in.")
    photo_count: int


class VisitPage(BaseModel):
    data: list[Visit]
    meta: PageMeta


class VisitPhoto(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    uploaded_at: str


# ── map and route ───────────────────────────────────────────────────────────

class OpenVisit(BaseModel):
    id: str
    label: str
    since: str


class TeamMember(BaseModel):
    user: UserRef
    role: str | None
    on_duty: bool
    last_seen_at: str | None
    lat: float | None = Field(description="Null when off duty.")
    lng: float | None
    accuracy_m: float | None
    battery_pct: int | None
    is_mock: bool
    stale: bool = Field(description="On duty and silent for 15 minutes.")
    open_visit: OpenVisit | None


class RoutePoint(BaseModel):
    at: str
    lat: float
    lng: float
    accuracy_m: float | None
    is_mock: bool


class Stop(BaseModel):
    from_: str = Field(alias="from")
    to: str
    minutes: int
    lat: float
    lng: float
    visit_id: str | None

    model_config = ConfigDict(populate_by_name=True)


class Route(BaseModel):
    user: UserRef
    date: str
    duty: list[Duty]
    points: list[RoutePoint] = Field(description="Oldest first, at most 2,000 for drawing.")
    stops: list[Stop] = Field(description="10 minutes or more within 150 m.")
    visits: list[Visit]
    distance_km: str = Field(description="One decimal, as a string.")
    point_count: int = Field(description="Every point of the day, before thinning.")
    dropped_points: int = Field(description="Left out: worse than 100 m, or an impossible jump.")
    mock_points: int


class ViewLogRow(BaseModel):
    viewer: UserRef
    subject: UserRef | None = Field(description="Null for the team map.")
    what: Literal["route", "visits", "team"]
    viewed_date: str | None
    viewed_at: str


class ViewLogPage(BaseModel):
    data: list[ViewLogRow]
    meta: PageMeta
