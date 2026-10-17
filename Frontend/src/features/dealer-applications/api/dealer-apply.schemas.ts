import { z } from "zod";

import {
  DEALER_APPLICATION_STATUSES,
  FIRM_TYPES,
  type FirmType,
} from "./dealer-applications.schemas";

/**
 * CHNL-008 · The applicant's own page (`/dealer-apply/<token>`, public): what the link shows
 * before the applicant verifies their mobile, and every field and document after
 * (`dealer_apply_view`). Contract: `docs/api/dealer-applications.md`, the `/public` calls.
 */

/** What an applicant uploads (`doc_type` on `POST …/documents`). */
export const APPLICANT_DOCUMENT_TYPES = [
  "gst_certificate",
  "pan_card",
  "cancelled_cheque",
  "shop_photo",
  "shop_licence",
  "other",
] as const;
export type ApplicantDocumentType = (typeof APPLICANT_DOCUMENT_TYPES)[number];

const documentWireSchema = z.object({
  id: z.string().min(1),
  doc_type: z.string(),
  name: z.string().nullable(),
  filename: z.string(),
  /** Uploaded by the applicant (staff uploads aren't theirs to remove). */
  mine: z.boolean(),
});

const applicantViewWireSchema = z.object({
  firm_name: z.string(),
  status: z.enum(DEALER_APPLICATION_STATUSES),
  /** "+91 xxxxxx3210" */
  mobile_masked: z.string(),
  missing: z.array(z.string()),
  /** The session sent is valid: the fields below are present. */
  session: z.boolean(),
  remark: z.string().nullish(),
  contact_name: z.string().optional(),
  firm_type: z.string().nullish(),
  gst_registered: z.boolean().optional(),
  gstin: z.string().nullish(),
  pan: z.string().nullish(),
  address: z.string().nullish(),
  pincode: z.string().nullish(),
  email: z.string().nullish(),
  godown_address: z.string().nullish(),
  years_in_business: z.number().int().nullish(),
  current_brands: z.string().nullish(),
  notes: z.string().nullish(),
  bank_account_name: z.string().nullish(),
  bank_account_no: z.string().nullish(),
  bank_ifsc: z.string().nullish(),
  documents: z.array(documentWireSchema).optional(),
});

function firmTypeOf(value: string | null | undefined): FirmType | null {
  return FIRM_TYPES.find((type) => type === value) ?? null;
}

export const applicantViewSchema = z
  .object({ data: applicantViewWireSchema })
  .transform(({ data }) => ({
    firmName: data.firm_name,
    status: data.status,
    mobileMasked: data.mobile_masked,
    missing: data.missing,
    verified: data.session,
    remark: data.remark ?? null,
    fields: data.session
      ? {
          firmName: data.firm_name,
          contactName: data.contact_name ?? "",
          firmType: firmTypeOf(data.firm_type),
          gstRegistered: data.gst_registered ?? true,
          gstin: data.gstin ?? null,
          pan: data.pan ?? null,
          address: data.address ?? null,
          pincode: data.pincode ?? null,
          email: data.email ?? null,
          godownAddress: data.godown_address ?? null,
          yearsInBusiness: data.years_in_business ?? null,
          currentBrands: data.current_brands ?? null,
          notes: data.notes ?? null,
          bankAccountName: data.bank_account_name ?? null,
          bankAccountNo: data.bank_account_no ?? null,
          bankIfsc: data.bank_ifsc ?? null,
        }
      : null,
    documents: (data.documents ?? []).map((document) => ({
      id: document.id,
      docType: document.doc_type,
      name: document.name,
      filename: document.filename,
      mine: document.mine,
    })),
  }));

export type ApplicantView = z.output<typeof applicantViewSchema>;
export type ApplicantDocument = ApplicantView["documents"][number];

export const applicantSessionSchema = z
  .object({ data: z.object({ session: z.string().min(1) }) })
  .transform(({ data }) => data.session);

export const codeSentSchema = z.object({ data: z.object({ sent: z.boolean() }) });

export const submittedSchema = z.object({ data: z.object({ submitted: z.boolean() }) });

export const uploadedSchema = z
  .object({ data: z.object({ id: z.string().min(1), created: z.boolean() }) })
  .transform(({ data }) => data);
