import { z } from "zod";

/**
 * CHNL-007 · Dealer applications (FS-053, sheet item 8): a prospective dealer is sent a link,
 * fills in the firm's, tax and bank details and uploads its documents, and a State Manager or
 * above approves it, which makes the dealer and its login. Contract:
 * `backend/docs/api/dealer-applications.md`, handover `dealer-recruitment-and-small-changes.md`.
 */

const id = z.string().min(1);

export const DEALER_APPLICATION_STATUSES = [
  "draft",
  "submitted",
  "returned",
  "approved",
  "rejected",
  "withdrawn",
] as const;
export type DealerApplicationStatus = (typeof DEALER_APPLICATION_STATUSES)[number];

/** Draft, returned and submitted are still open; the rest are closed. */
export const OPEN_STATUSES: readonly DealerApplicationStatus[] = ["draft", "returned", "submitted"];

export const FIRM_TYPES = ["proprietorship", "partnership", "llp", "company"] as const;
export type FirmType = (typeof FIRM_TYPES)[number];

const userRef = z.object({ id, full_name: z.string() });

const rowWireSchema = z.object({
  id,
  status: z.enum(DEALER_APPLICATION_STATUSES),
  firm_name: z.string(),
  contact_name: z.string(),
  territory_name: z.string(),
  created_at: z.string().min(1),
  submitted_at: z.string().nullable(),
});

export const dealerApplicationListSchema = z
  .object({ data: z.array(rowWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({
      id: row.id,
      status: row.status,
      firmName: row.firm_name,
      contactName: row.contact_name,
      territoryName: row.territory_name,
      createdAt: row.created_at,
      submittedAt: row.submitted_at,
    })),
  );

export type DealerApplicationRow = z.output<typeof dealerApplicationListSchema>[number];

const gstLookupSchema = z.object({
  valid: z.boolean(),
  lookup: z.string(),
  legal_name: z.string().nullish(),
  trade_name: z.string().nullish(),
});

export const dealerApplicationWireSchema = z.object({
  id,
  status: z.enum(DEALER_APPLICATION_STATUSES),
  firm_name: z.string(),
  contact_name: z.string(),
  mobile: z.string(),
  territory: z.object({ id, name: z.string() }),
  lead_id: z.string().nullable(),
  firm_type: z.string().nullable(),
  gst_registered: z.boolean(),
  gstin: z.string().nullable(),
  pan: z.string().nullable(),
  address: z.string().nullable(),
  pincode: z.string().nullable(),
  email: z.string().nullable(),
  godown_address: z.string().nullable(),
  years_in_business: z.number().int().nullable(),
  current_brands: z.string().nullable(),
  notes: z.string().nullable(),
  bank_account_name: z.string().nullable(),
  /** Masked to the last four digits unless the reader may decide or edit partners. */
  bank_account_no: z.string().nullable(),
  bank_ifsc: z.string().nullable(),
  gst_lookup: gstLookupSchema.nullable(),
  /** The GSTIN's state isn't the territory's. */
  gst_state_mismatch: z.boolean(),
  /** What is still needed to submit: field names and document types. */
  missing: z.array(z.string()),
  partner_id: z.string().nullable(),
  user_id: z.string().nullable(),
  decided_by: userRef.nullable(),
  decided_at: z.string().nullable(),
  decision_remark: z.string().nullable(),
  link_expires_at: z.string().min(1),
  /** Only right after creating it or renewing the link: the token isn't stored. */
  apply_url: z.string().nullish(),
  created_by: userRef.nullable(),
  created_at: z.string().min(1),
  can: z.object({
    edit: z.boolean(),
    decide: z.boolean(),
    withdraw: z.boolean(),
    renew: z.boolean(),
  }),
});

export type DealerApplicationWire = z.input<typeof dealerApplicationWireSchema>;

function firmTypeOf(value: string | null): FirmType | null {
  return FIRM_TYPES.find((type) => type === value) ?? null;
}

export const dealerApplicationSchema = z
  .object({ data: dealerApplicationWireSchema })
  .transform(({ data }) => ({
    id: data.id,
    status: data.status,
    firmName: data.firm_name,
    contactName: data.contact_name,
    mobile: data.mobile,
    territory: data.territory,
    leadId: data.lead_id,
    firmType: firmTypeOf(data.firm_type),
    gstRegistered: data.gst_registered,
    gstin: data.gstin,
    pan: data.pan,
    address: data.address,
    pincode: data.pincode,
    email: data.email,
    godownAddress: data.godown_address,
    yearsInBusiness: data.years_in_business,
    currentBrands: data.current_brands,
    notes: data.notes,
    bankAccountName: data.bank_account_name,
    bankAccountNo: data.bank_account_no,
    bankIfsc: data.bank_ifsc,
    gstNames:
      data.gst_lookup === null
        ? null
        : {
            legalName: data.gst_lookup.legal_name?.trim() || null,
            tradeName: data.gst_lookup.trade_name?.trim() || null,
          },
    gstStateMismatch: data.gst_state_mismatch,
    missing: data.missing,
    partnerId: data.partner_id,
    decidedBy: data.decided_by === null ? null : { name: data.decided_by.full_name },
    decidedAt: data.decided_at,
    decisionRemark: data.decision_remark,
    linkExpiresAt: data.link_expires_at,
    applyUrl: data.apply_url ?? null,
    createdBy: data.created_by === null ? null : { name: data.created_by.full_name },
    createdAt: data.created_at,
    can: data.can,
  }));

export type DealerApplication = z.output<typeof dealerApplicationSchema>;

// ── writes ─────────────────────────────────────────────────────────────────────────

export interface DealerApplicationListParams {
  /** Empty: every status. */
  readonly status: readonly DealerApplicationStatus[];
  readonly q: string;
}

/** POST /dealer-applications. The mobile becomes the dealer's login. */
export interface CreateDealerApplicationRequest {
  readonly firm_name: string;
  readonly contact_name: string;
  readonly mobile: string;
  readonly territory_id: string;
  readonly lead_id?: string;
}

/** PATCH /dealer-applications/{id}: only what changes; null clears. */
export interface DealerApplicationFieldsRequest {
  readonly firm_name?: string;
  readonly contact_name?: string;
  readonly firm_type?: FirmType | null;
  readonly gst_registered?: boolean;
  readonly gstin?: string | null;
  readonly pan?: string | null;
  readonly address?: string | null;
  readonly pincode?: string | null;
  readonly email?: string | null;
  readonly godown_address?: string | null;
  readonly years_in_business?: number | null;
  readonly current_brands?: string | null;
  readonly notes?: string | null;
  readonly bank_account_name?: string | null;
  readonly bank_account_no?: string | null;
  readonly bank_ifsc?: string | null;
}

export const DECISIONS = ["approve", "return", "reject"] as const;
export type Decision = (typeof DECISIONS)[number];

/** POST /dealer-applications/{id}/decision. A remark is needed to return or reject. */
export interface DecisionRequest {
  readonly decision: Decision;
  readonly remark: string | null;
  /** An active distributor; null: directly under Polysil. */
  readonly parent_id: string | null;
  /** The partner code; null: the next DLR-<state>-0001. */
  readonly code: string | null;
}

export interface RemarkRequest {
  readonly remark: string;
}
