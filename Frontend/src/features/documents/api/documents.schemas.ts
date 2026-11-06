import { z } from "zod";

/**
 * DOC-001…003 · Documents on records (FS-050): a named file — a purchase order, a payment
 * slip, an invoice, a photo — on a lead, quotation, sales order, dispatch or payment.
 * Contract: `backend/docs/api/documents.md`, handover `documents-and-replacement-chain.md`.
 */

export const RECORD_TYPES = [
  "lead",
  "quotation",
  "sales_order",
  "dispatch",
  "payment",
  "dealer_application",
] as const;
export type RecordType = (typeof RECORD_TYPES)[number];

/** Which documents: one record's, or a lead's with everything made from it. */
export type DocumentsScope =
  | { readonly kind: "lead"; readonly leadId: string }
  | { readonly kind: "record"; readonly recordType: RecordType; readonly recordId: string };

/** JPEG, PNG, WebP, HEIC or PDF; the backend judges the content, not the name. */
export const DOCUMENT_CONTENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
  "application/pdf",
] as const;
export const DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
export const DOCUMENTS_PER_RECORD = 50;
/** A document's own name: required for "other", a note otherwise. */
export const DOCUMENT_NAME_MAX = 80;

const documentWireSchema = z.object({
  id: z.string().min(1),
  record_type: z.enum(RECORD_TYPES),
  record_id: z.string().min(1),
  /** The inquiry, quote, order or dispatch number, on the lead view. */
  record_label: z.string().nullish(),
  /** A string, not an enum: a new type from the backend still shows, by its label. */
  doc_type: z.string().min(1),
  doc_type_label: z.string(),
  name: z.string().nullable(),
  filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  /** False for HEIC, which browsers cannot show. */
  preview: z.boolean(),
  uploaded_by: z.object({ id: z.string().min(1), full_name: z.string() }).nullable(),
  uploaded_at: z.string().min(1),
});

export type RecordDocumentWire = z.input<typeof documentWireSchema>;

export interface RecordDocument {
  readonly id: string;
  readonly recordType: RecordType;
  readonly recordId: string;
  readonly recordLabel: string | null;
  readonly docType: string;
  readonly docTypeLabel: string;
  readonly name: string | null;
  readonly filename: string;
  readonly contentType: string;
  readonly sizeBytes: number;
  readonly preview: boolean;
  readonly uploadedBy: { readonly id: string; readonly name: string } | null;
  readonly uploadedAt: string;
}

function toDocument(wire: z.output<typeof documentWireSchema>): RecordDocument {
  return {
    id: wire.id,
    recordType: wire.record_type,
    recordId: wire.record_id,
    recordLabel: wire.record_label ?? null,
    docType: wire.doc_type,
    docTypeLabel: wire.doc_type_label,
    name: wire.name,
    filename: wire.filename,
    contentType: wire.content_type,
    sizeBytes: wire.size_bytes,
    preview: wire.preview,
    uploadedBy:
      wire.uploaded_by === null
        ? null
        : { id: wire.uploaded_by.id, name: wire.uploaded_by.full_name },
    uploadedAt: wire.uploaded_at,
  };
}

export const documentListSchema = z
  .object({ data: z.array(documentWireSchema) })
  .transform(({ data }) => data.map(toDocument));

export const documentSchema = z
  .object({ data: documentWireSchema })
  .transform(({ data }) => toDocument(data));

const documentTypeSchema = z.object({
  code: z.string().min(1),
  label: z.string(),
  /** True for "other": the user names the document. */
  needs_name: z.boolean(),
});

export type DocumentTypeWire = z.input<typeof documentTypeSchema>;

export const documentTypesSchema = z
  .object({ data: z.array(documentTypeSchema) })
  .transform(({ data }) =>
    data.map((type) => ({ code: type.code, label: type.label, needsName: type.needs_name })),
  );

export type DocumentType = z.output<typeof documentTypesSchema>[number];

/** A ten-minute link to the file. Never fetched with the bearer token. */
export const documentLinkSchema = z
  .object({
    data: z.object({
      url: z.string().min(1),
      expires_at: z.string(),
      filename: z.string(),
      content_type: z.string(),
    }),
  })
  .transform(({ data }) => ({
    url: data.url,
    expiresAt: data.expires_at,
    filename: data.filename,
  }));

export type DocumentLink = z.output<typeof documentLinkSchema>;
