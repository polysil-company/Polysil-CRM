"""Response shape for GET /dashboard/overview (FS-017).

Every figure is a decimal string, money and percentages alike (rule 4). Field
descriptions become the field notes in the generated API doc.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.schemas.leads import Stage, UserRef


class Kpi(BaseModel):
    value: str | None = Field(description="The figure, a decimal string. Null only for "
                              "`overdue_follow_ups` when you have no task permission.")
    delta_percent: str | None = Field(
        description="(current - previous) / previous x 100, one decimal. Null when the "
        "previous period is zero, and always for a snapshot figure.")
    trend: list[str] = Field(description="Oldest first, one entry per bucket of the period. "
                             "Empty for a snapshot figure.")


class Kpis(BaseModel):
    pipeline_value: Kpi = Field(description="Summed estimated value of open leads, now.")
    new_leads: Kpi = Field(description="Leads created in the period.")
    conversion_rate: Kpi = Field(description="Of the period's new leads, the percentage won now.")
    overdue_follow_ups: Kpi = Field(description=(
        "Open tasks **on leads** you can see, matching the dashboard's filters, due in the "
        "90 days before today: the same figure as follow_ups_overdue on GET /leads/stats. "
        "A task with no lead, or on a dealer, is not counted, so it can be lower than "
        "Tasks → My day, which counts every open task assigned to you (FS-073, BE-036). "
        "Label it \"Overdue follow-ups on leads\"."))


class Period(BaseModel):
    start: str = Field(description="The first IST date of the period.")
    end: str = Field(description="The last IST date, today.")


class PipelineStage(BaseModel):
    stage: Stage
    count: int
    value: str = Field(description="Summed estimated value, a decimal string.")


class SourceCount(BaseModel):
    source: str = Field(description="The lead source code.")
    name: str
    count: int = Field(description="Leads created in the period from this source.")


class FollowUp(BaseModel):
    task_id: str
    lead_id: str
    farmer_name: str
    district: str | None = Field(description="The district above the lead's territory.")
    due_at: str
    assigned_to: UserRef | None = Field(
        description="The task's assignee. `full_name` is empty for someone outside your "
        "view of people.")
    overdue: bool = Field(description="Due before today (IST).")


class SystemArea(BaseModel):
    system: str = Field(description="The irrigation system's code.")
    name: str
    leads: int = Field(description="Open and won leads now with this system.")
    hectares: str = Field(description="Their land, summed, a decimal string. Leads without "
                                      "land add nothing.")


class MonthTarget(BaseModel):
    month: str = Field(description="YYYY-MM.")
    target: str = Field(description="The order value target, summed over your team. \"0.00\" "
                                    "when nobody has one.")
    achieved: str | None = Field(description="Order value counted as sold that month. Null "
                                             "without a sales orders permission.")


class DashboardOverview(BaseModel):
    period_label: str
    period: Period
    kpis: Kpis
    pipeline: list[PipelineStage] = Field(description="Every stage but merged, in lifecycle order.")
    sources: list[SourceCount]
    area_by_system: list[SystemArea] = Field(
        default_factory=list, description="Open and won leads now, by irrigation system "
                                          "(FS-052). Systems with none are left out.")
    targets_by_month: list[MonthTarget] | None = Field(
        default=None, description="This month and the five before it, oldest first: order "
                                  "value target against what was sold. Null without a targets "
                                  "permission (FS-052).")
    follow_ups: list[FollowUp] = Field(
        description="The 10 earliest-due open tasks on your leads. Empty without a task "
        "permission.")
