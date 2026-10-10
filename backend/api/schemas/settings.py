"""Company settings (FS-036): one row per setting, its value and the rule for it."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SettingValue = str | int | list[str] | list[int]


class Setting(BaseModel):
    key: str
    kind: Literal["choice", "int", "roles", "bands"] = Field(
        description="choice: one of `allowed`; int: a whole number in `min`..`max`; "
                    "roles: a list of role codes; bands: four whole numbers, zero or more, "
                    "strictly rising (FS-043).")
    value: SettingValue
    allowed: list[str] | None = Field(description="The choices, for a choice setting.")
    min: int | None
    max: int | None
    description: str
    updated_at: str


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: Annotated[dict[str, SettingValue], Field(
        min_length=1, description="Only the settings that change, by key.")]
