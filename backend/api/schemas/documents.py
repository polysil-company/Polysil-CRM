# ruff: noqa: E501  (embedded SQL and field declarations)

"""Documents on records (FS-050): a named file on a lead, quotation, sales order,
dispatch or payment."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

from api.schemas.leads import UserRef

RecordType = Literal["lead", "quotation", "sales_order", "dispatch", "payment", "dealer_application"]
DocType = Literal["purchase_order", "payment_proof", "signed_quotation", "invoice", "delivery_challan",
                  "transport_receipt", "site_photo", "land_record", "subsidy_document", "other",
                  "gst_certificate", "pan_card", "cancelled_cheque", "shop_photo", "shop_licence"]

DOC_TYPE_LABELS: Final[dict[str, str]] = {
    "purchase_order": "Purchase order",
    "payment_proof": "Payment slip or receipt",
    "signed_quotation": "Signed quotation",
    "invoice": "Invoice",
    "delivery_challan": "Delivery challan",
    "transport_receipt": "Transport receipt (LR)",
    "site_photo": "Site or installation photo",
    "land_record": "Land record (7/12 or similar)",
    "subsidy_document": "Subsidy document",
    "other": "Other",
    # FS-051: a dealer application's documents
    "gst_certificate": "GST certificate",
    "pan_card": "PAN card",
    "cancelled_cheque": "Cancelled cheque",
    "shop_photo": "Shop photo",
    "shop_licence": "Shop licence",
}


class RecordDocumentType(BaseModel):
    code: str
    label: str
    needs_name: bool = Field(description="True for `other`: the user names the document.")


class RecordDocument(BaseModel):
    id: str
    record_type: RecordType
    record_id: str
    record_label: str | None = Field(default=None, description="The inquiry, quote, order or dispatch "
                                                             "number, on the lead view.")
    doc_type: DocType
    doc_type_label: str
    name: str | None = Field(description="The user's name for it; always set for `other`.")
    filename: str
    content_type: str
    size_bytes: int
    preview: bool = Field(description="False for HEIC, which browsers cannot show.")
    uploaded_by: UserRef | None
    uploaded_at: str


class RecordDocumentLink(BaseModel):
    url: str = Field(description="Valid ten minutes. Never fetch it with the bearer token.")
    expires_at: str
    filename: str
    content_type: str
