"""The in-app assistant (FS-045): actions and records for one search box."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.domain.assistant import Screen

RecordKind = Literal["lead", "customer", "quotation", "sales_order", "complaint"]


class AssistantAction(BaseModel):
    key: str
    title: str
    hint: str
    screen: Screen = Field(description="A stable key; the frontend maps it to its own route.")
    module: str


class AssistantRecord(BaseModel):
    kind: RecordKind = Field(description="The same words as a notification's resource.type.")
    id: str
    label: str
    screen: Screen = Field(description="Open with this id.")


class AssistantAnswer(BaseModel):
    actions: list[AssistantAction]
    records: list[AssistantRecord]
