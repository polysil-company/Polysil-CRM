"""Ratings (FS-043): feedback entered on an installation, a service visit or a
product, and the dealer rating derived from payment days and order value."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.leads import UUID_RE, PageMeta, PartnerRef, UserRef

Target = Literal["installation", "service", "product"]
RatedBy = Literal["customer", "dealer"]


class RatingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    sales_order_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Installation and product: the order.")]
    complaint_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Service: the closed complaint.")]
    product_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Product: a product shipped on the order.")]
    score: Annotated[int, Field(ge=1, le=5, description="1 to 5 stars.")]
    comment: Annotated[str | None, Field(default=None, max_length=1000,
                                         description="Optional. Trimmed; blank is none.")]

    @model_validator(mode="after")
    def _fields_for_target(self) -> RatingCreate:
        need = {"installation": ("sales_order_id",), "product": ("sales_order_id", "product_id"),
                "service": ("complaint_id",)}[self.target]
        sent = {f for f in ("sales_order_id", "complaint_id", "product_id")
                if getattr(self, f) is not None}
        if sent != set(need):
            raise ValueError(f"a {self.target} rating takes {' and '.join(need)} only")
        return self


class RatingDoc(BaseModel):
    id: str
    number: str | None = Field(description="The order or complaint number.")
    status: str = Field(description="The document's status now; a rating stays if it goes back.")


class RatingProduct(BaseModel):
    id: str
    description: str


class RatingLead(BaseModel):
    id: str
    inquiry_no: str | None


class Rating(BaseModel):
    id: str
    target: Target
    score: int
    comment: str | None = Field(description="Null for a dealer reading a customer's rating "
                                            "(GAP-375), or when none was given.")
    rated_by: RatedBy
    entered_by: UserRef | None = Field(description="Null for a dealer reading a customer's rating.")
    partner: PartnerRef | None
    lead: RatingLead | None
    order: RatingDoc | None
    complaint: RatingDoc | None
    product: RatingProduct | None
    created_at: str


class RatingPage(BaseModel):
    data: list[Rating]
    meta: PageMeta


class SummaryKey(BaseModel):
    id: str
    name: str


class SummaryRow(BaseModel):
    key: SummaryKey
    count: int
    average: str = Field(description="To two decimals.")
    low: int = Field(description="Ratings of 1 or 2.")


class Feedback(BaseModel):
    count: int
    average: str | None


class DealerRating(BaseModel):
    partner_id: str
    on: str = Field(description="Today in India: the rating is computed on every read.")
    window_days: int
    orders: int = Field(description="The dealer's commercial and industrial orders submitted in "
                                    "the window, in a payable status.")
    paid_orders: int
    payment_days: str | None = Field(description="Value-weighted days from order to full payment, "
                                                 "one decimal. Null when no order counts.")
    payment_score: int | None
    order_value: str = Field(description="Taxable value, before GST.")
    value_score: int | None
    rating: str | None = Field(description="The mean of the two scores, one decimal.")
    feedback: Feedback = Field(description="Customers' ratings of the dealer's documents only.")
