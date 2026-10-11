"""Subsidy schemes (FS-039): a new state's scheme, its readiness, the lead's scheme."""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from api.schemas.subsidy import SystemType

UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
# upper-cased before the pattern runs: StringConstraints checks the pattern first
Code = Annotated[str, BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
                 StringConstraints(pattern=r"^[A-Z0-9_]{2,20}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class SchemeState(BaseModel):
    id: str
    code: str
    name: str


class SchemeRow(BaseModel):
    code: str
    name: str
    is_active: bool
    state: SchemeState | None = Field(description="Null: the scheme is not tied to a state.")
    systems: list[SystemType]
    ready: bool = Field(description="Every active system can calculate today and an "
                                    "application can start.")
    applications: int = Field(description="Applications on the scheme the caller can see, "
                                          "cancelled included.")


class SystemReadiness(BaseModel):
    system_type: SystemType
    ready: bool
    missing: list[str] = Field(description=(
        "What a calculation would refuse on, in the order it would refuse: "
        "`unit_cost_matrix:regular`, `unit_cost_matrix:seven_year`, `categories`, "
        "`crop_spacings`, `quantity_matrix`, `quantity_matrix:<row>`, `parameters:<key>`, "
        "`component_rate:<code>[:<size or nozzle>]`."))


class StageOut(BaseModel):
    seq: int
    code: str
    name: str
    is_active: bool


class SchemeDetail(BaseModel):
    code: str
    name: str
    is_active: bool
    state: SchemeState | None
    on: str = Field(description="The date readiness was checked for (IST).")
    systems: list[SystemReadiness]
    stages: list[StageOut]
    ready: bool = Field(description="Every active system ready, and at least one active stage.")


class SubsidySchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code = Field(description="2 to 20 of A-Z, 0-9 and _. Stored upper case.")
    name: Name
    state_territory_id: Annotated[str, Field(pattern=UUID_RE, description="A state.")]
    template: Code = Field(default="GGRC", description="The scheme whose engine settings "
                                                      "and stages are copied. No figure is copied.")
    systems: list[SystemType] | None = Field(default=None, min_length=1, description=(
        "A subset of the template's systems. Default: all of them."))


class SchemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    is_active: bool | None = None
    state_territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE, description=(
        "Accepted only while the scheme has no state: how GGRC is linked to Gujarat."))]

    @model_validator(mode="after")
    def _something(self) -> SchemeUpdate:
        if self.name is None and self.is_active is None and self.state_territory_id is None:
            raise ValueError("send at least one of name, is_active, state_territory_id")
        return self


class StageRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name


class LeadScheme(BaseModel):
    code: str
    name: str
    ready: bool
