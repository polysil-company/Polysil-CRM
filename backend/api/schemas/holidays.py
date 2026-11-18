"""Holidays: days complaint targets skip like Sundays (FS-028)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class Holiday(BaseModel):
    day: dt.date = Field(description="The day, IST. Never a Sunday.")
    name: str = Field(description="What the day is, e.g. Diwali.")


class HolidayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: dt.date = Field(description="A day after today (IST), not a Sunday.")
    name: str = Field(min_length=1, max_length=80,
                      description="What the day is, 1 to 80 characters.")
