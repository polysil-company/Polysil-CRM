"""Seller GSTINs and their LUTs (FS-042): the registrations we sell from, and the
letters of undertaking that zero-rate their exports."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

# upper-cased before the pattern runs: StringConstraints checks the pattern first
Arn = Annotated[str, BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
                StringConstraints(pattern=r"^[A-Z0-9]{10,20}$")]


class Lut(BaseModel):
    id: str
    arn: str = Field(description="The LUT's acknowledgement reference number.")
    valid_from: dt.date
    valid_to: dt.date
    in_use: bool = Field(description="A quotation or order carries this LUT, so it cannot be "
                                     "removed.")


class SellerGstin(BaseModel):
    id: str
    gstin: str
    legal_name: str
    state_code: str
    is_default: bool
    is_active: bool
    luts: list[Lut] = Field(description="Newest year first.")


class LutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arn: Arn = Field(description="10 to 20 letters and digits. Stored upper case.")
    valid_from: dt.date = Field(description="On or after 1 April of the LUT's financial year.")
    valid_to: dt.date = Field(description="On or before 31 March of the same financial year.")
