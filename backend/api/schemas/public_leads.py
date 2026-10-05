"""Shapes for the public lead form and the staff QR codes (FS-003a §4).

The public shapes carry nothing about existing data beyond the caller's own
inquiry number, and only after the WhatsApp code matched (rule 6).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PartnerRef, TerritoryRef


class PublicQr(BaseModel):
    code: str
    label: str = Field(description="The dealer or place the code was printed for.")
    campaign: str | None
    territory_id: str | None = Field(description="Preselect this territory in the picker.")


class PublicState(BaseModel):
    id: str
    name: str


class PublicSystem(BaseModel):
    code: str
    name: str


class PublicLeadForm(BaseModel):
    qr: PublicQr | None = Field(description="Null when the page was opened without a code.")
    states: list[PublicState]
    mis_systems: list[PublicSystem]
    inquiry_types: list[str]


class PublicTerritory(BaseModel):
    id: str
    name: str
    level: str = Field(description="district, taluka or village.")


class VerifyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    mobile: Annotated[str, Field(min_length=10, max_length=20,
                                 description="Any Indian form: 9876543210, +91 98765 43210.")]


class VerifySent(BaseModel):
    """The same body whatever happened, so it never says whether a number is known."""

    sent: bool = True
    channel: Literal["whatsapp"] = "whatsapp"
    expires_in: int = Field(description="Seconds the code is valid.")
    resend_after: int = Field(description="Seconds before offering to send another.")


class PublicLeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    mobile: Annotated[str, Field(min_length=10, max_length=20)]
    code: Annotated[str, Field(pattern=r"^\d{6}$", description="The six digits from WhatsApp.")]
    farmer_name: Annotated[str, Field(min_length=1, max_length=200)]
    territory_id: Annotated[str, Field(pattern=UUID_RE,
                                       description="A district or taluka, never a state.")]
    village: Annotated[str | None, Field(default=None, max_length=120)]
    mis_system: Annotated[str, Field(min_length=1, max_length=40)]
    inquiry_type: Literal["commercial", "subsidised", "industrial"] = "commercial"
    note: Annotated[str | None, Field(default=None, max_length=1000)]
    qr: Annotated[str | None, Field(default=None, max_length=12,
                                    description="The code from the page URL, if any.")]


class PublicLeadResult(BaseModel):
    inquiry_no: str = Field(description="Show it to the farmer; it also goes by WhatsApp.")
    created: bool = Field(description="False when this mobile already enquired today "
                                      "through the form: the earlier number is returned.")


class QrCodeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    label: Annotated[str, Field(min_length=1, max_length=120,
                                description="What staff will recognise: the dealer, the "
                                            "stall, the leaflet.")]
    campaign: Annotated[str | None, Field(default=None, max_length=120)]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Leads from this code are assigned to this partner.")]
    territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Preselected in the form's picker.")]


class QrCodePatch(BaseModel):
    """Any subset. A field sent null is cleared; the label cannot be. The six
    characters never change: they are printed (FS-035 rule 1)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    label: Annotated[str | None, Field(default=None, min_length=1, max_length=120)]
    campaign: Annotated[str | None, Field(default=None, max_length=120)]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="New leads from this code go to this partner; earlier leads keep theirs.")]
    territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Preselected in the form's picker.")]
    is_active: Annotated[bool | None, Field(
        default=None, description="false switches the code off: the form then makes a "
                                  "plain website enquiry.")]


class QrCode(BaseModel):
    id: str
    code: str = Field(description="Six characters, no look-alikes.")
    url: str = Field(description="What the printed QR encodes; the frontend draws it.")
    label: str
    campaign: str | None
    partner: PartnerRef | None
    territory: TerritoryRef | None
    is_active: bool
    lead_count: int = Field(description="Leads this code has brought, in your scope.")
    created_at: str


class QrCodeList(BaseModel):
    data: list[QrCode]
