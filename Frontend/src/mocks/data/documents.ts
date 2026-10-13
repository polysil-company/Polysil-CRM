import type {
  DocumentTypeWire,
  RecordDocumentWire,
} from "@/features/documents/api/documents.schemas";
import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";

import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "./reference";

/**
 * DOC-001 · Documents on records, as the mock keeps them. The types and labels are the
 * backend's (`api/schemas/documents.py`), the dealer application's five included.
 */
export const MOCK_DOCUMENT_TYPES: readonly DocumentTypeWire[] = [
  ["purchase_order", "Purchase order"],
  ["payment_proof", "Payment slip or receipt"],
  ["signed_quotation", "Signed quotation"],
  ["invoice", "Invoice"],
  ["delivery_challan", "Delivery challan"],
  ["transport_receipt", "Transport receipt (LR)"],
  ["site_photo", "Site or installation photo"],
  ["land_record", "Land record (7/12 or similar)"],
  ["subsidy_document", "Subsidy document"],
  ["other", "Other"],
  ["gst_certificate", "GST certificate"],
  ["pan_card", "PAN card"],
  ["cancelled_cheque", "Cancelled cheque"],
  ["shop_photo", "Shop photo"],
  ["shop_licence", "Shop licence"],
].map(([code = "", label = ""]) => ({ code, label, needs_name: code === "other" }));

export function mockDocumentTypeLabel(code: string): string | undefined {
  return MOCK_DOCUMENT_TYPES.find((type) => type.code === code)?.label;
}

/** A document with what the mock needs to find a repeat upload and hide a removed one. */
export interface MockDocument extends RecordDocumentWire {
  /** Stands in for the backend's SHA-256 of the bytes: the file's name and size. */
  readonly fingerprint: string;
  removed: boolean;
}

/**
 * A few documents on one lead's whole story: a site photo on the lead, the signed quotation,
 * the order's purchase order and a payment slip photographed on an iPhone (HEIC, no preview),
 * and the transport receipt on its dispatch.
 */
export function seedDocuments(
  leads: readonly LeadWire[],
  quotations: readonly QuotationWire[],
  orders: readonly OrderWire[],
): MockDocument[] {
  const order = orders.find(
    (item) => item.lead !== null && item.dispatches.length > 0 && item.quotations.length > 0,
  );
  const lead = leads.find((item) => item.id === order?.lead?.id);
  const quotation = quotations.find((item) => item.id === order?.quotations[0]?.id);
  const dispatch = order?.dispatches[0];
  if (
    order === undefined ||
    lead === undefined ||
    quotation === undefined ||
    dispatch === undefined
  ) {
    return [];
  }
  const asha = MOCK_STAFF[1] ?? { id: "", full_name: "" };
  let index = 0;
  const make = (
    record: Pick<RecordDocumentWire, "record_type" | "record_id">,
    docType: string,
    file: { name: string; type: string; size: number },
    uploadedAt: string,
    name: string | null = null,
  ): MockDocument => {
    index += 1;
    return {
      id: mockUuid(MOCK_ID_SPACE.document, index),
      ...record,
      record_label: null,
      doc_type: docType,
      doc_type_label: mockDocumentTypeLabel(docType) ?? docType,
      name,
      filename: file.name,
      content_type: file.type,
      size_bytes: file.size,
      preview: file.type !== "image/heic" && file.type !== "image/heif",
      uploaded_by: { id: asha.id, full_name: asha.full_name },
      uploaded_at: uploadedAt,
      fingerprint: `${file.name}:${String(file.size)}`,
      removed: false,
    };
  };
  // Newest first, as the backend lists them.
  return [
    make(
      { record_type: "dispatch", record_id: dispatch.id },
      "transport_receipt",
      { name: "LR-88213.pdf", type: "application/pdf", size: 182_340 },
      "2026-10-09T09:15:00Z",
    ),
    make(
      { record_type: "sales_order", record_id: order.id },
      "payment_proof",
      { name: "IMG_4412.HEIC", type: "image/heic", size: 2_412_544 },
      "2026-10-06T11:40:00Z",
      "Advance, NEFT",
    ),
    make(
      { record_type: "sales_order", record_id: order.id },
      "purchase_order",
      { name: "PO-4471.pdf", type: "application/pdf", size: 96_120 },
      "2026-10-05T06:20:00Z",
    ),
    make(
      { record_type: "quotation", record_id: quotation.id },
      "signed_quotation",
      { name: "signed-quotation.pdf", type: "application/pdf", size: 311_802 },
      "2026-10-03T08:05:00Z",
    ),
    make(
      { record_type: "lead", record_id: lead.id },
      "site_photo",
      { name: "farm-borewell.jpg", type: "image/jpeg", size: 845_210 },
      "2026-09-28T07:30:00Z",
    ),
  ];
}
