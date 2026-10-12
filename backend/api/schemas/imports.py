"""Excel import (FS-062): upload, match columns, check, commit."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImportKind = Literal["partners", "price_list_items", "lines"]
ImportStatus = Literal["uploaded", "checked", "committed", "discarded"]


class ImportField(BaseModel):
    key: str = Field(description="What the mapping names.")
    label: str = Field(description="What the matching screen shows.")
    required: bool
    help: str = Field(description="One line under the dropdown. May be empty.")


class ImportRowError(BaseModel):
    row: int = Field(description="The row number in the person's sheet.")
    errors: dict[str, str] = Field(description="Field key to the reason.")


class ImportPreviewRow(BaseModel):
    row: int
    values: dict[str, object] = Field(
        description="The row as it will be saved: normalised (a mobile as 91XXXXXXXXXX, "
                    "money with two decimals), with names for the looked-up values.")


class ImportLine(BaseModel):
    """A good row of a `lines` import, ready for the line editor."""

    row: int
    product_id: str
    product: str = Field(description="The product's description.")
    qty: str
    discount_pct: str
    discount2_pct: str
    discount3_pct: str


class ImportCheck(BaseModel):
    total: int
    ok: int
    errors: int = Field(description="Rows with at least one error. The true count, even when "
                                    "`error_rows` is cut at 500.")
    error_rows: list[ImportRowError] = Field(description="At most 500, in sheet order.")
    preview: list[ImportPreviewRow] = Field(description="The first 20 good rows.")
    column_warnings: dict[str, str] = Field(
        description="Field key to a message about the whole column: empty on every row, or "
                    "formulas with no saved result. Show it beside the dropdown.")
    lines: list[ImportLine] | None = Field(
        description="`lines` imports only: every good row, for the line editor.")


class ImportBatch(BaseModel):
    id: str
    kind: ImportKind
    status: ImportStatus
    target_id: str | None = Field(description="The draft price list, for price_list_items.")
    file_name: str
    sheet: str | None = Field(description="Null for a CSV.")
    sheets: list[str] = Field(description="Every sheet in the workbook. Empty for a CSV.")
    header_row: int
    row_count: int
    headers: list[str] = Field(description="Column headers. A blank one reads `Column C`; a "
                                           "repeated one gets ` (2)`.")
    sample: list[list[str]] = Field(description="The first five rows, cell by cell.")
    fields: list[ImportField]
    suggested_mapping: dict[str, int] = Field(
        description="Field key to column index (0-based into `headers`). From your last "
                    "import of this kind, then from common header names. Absent means no guess.")
    mapping: dict[str, int] | None = Field(description="The mapping last checked.")
    check: ImportCheck | None = Field(description="The last check.")
    created_at: dt.datetime


class ImportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["replace", "merge"] = Field(
        default="replace",
        description="price_list_items only. replace: the file becomes the whole list. merge: "
                    "the list keeps its rates for products not in the file.")


class ImportCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping: dict[str, int] = Field(description="Field key to column index (0-based).")
    options: ImportOptions = Field(default_factory=ImportOptions)


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skip_invalid: bool = Field(
        default=False,
        description="Save the good rows and skip the bad ones. Without it, any bad row "
                    "refuses the whole import.")


class ImportCommitResult(BaseModel):
    status: ImportStatus
    created: int = Field(description="Partners created, or rates written.")
    skipped: int
    price_list_id: str | None = None
