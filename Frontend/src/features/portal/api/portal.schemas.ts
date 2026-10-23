import { z } from "zod";

/**
 * FARM-001 … FARM-003 · The farmers' portal (FS-044, `consumer-portal.md`, generated
 * `portal.md`). A farmer signs in with their mobile and a WhatsApp code and sees their own
 * record: read-only, plus consent and their ratings. Off by default.
 */

const isoDateTime = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

const meWireSchema = z.object({
  name: z.string(),
  mobile: z.string(),
  email: z.string().nullable(),
  village: z.string().nullable(),
  territory_name: z.string().nullable(),
  consent_given_at: isoDateTime.nullable(),
  consent_channel: z.string().nullable(),
});
export type PortalMeWire = z.input<typeof meWireSchema>;

export const portalMeSchema = z.object({ data: meWireSchema }).transform(({ data }) => ({
  name: data.name,
  mobile: data.mobile,
  email: data.email,
  village: data.village,
  territoryName: data.territory_name,
  consentGivenAt: data.consent_given_at,
  consentChannel: data.consent_channel,
}));
export type PortalMe = z.output<typeof portalMeSchema>;

const enquiryWireSchema = z.object({
  inquiry_no: z.string(),
  /** in_progress, won or closed. */
  status: z.string(),
  /** The irrigation system asked about. */
  system: z.string(),
  created_at: isoDateTime,
});
export type PortalEnquiryWire = z.input<typeof enquiryWireSchema>;

export const portalEnquiriesSchema = z
  .object({ data: z.array(enquiryWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({
      code: row.inquiry_no,
      status: row.status,
      system: row.system,
      createdAt: row.created_at,
    })),
  );
export type PortalEnquiry = z.output<typeof portalEnquiriesSchema>[number];

const quotationWireSchema = z.object({
  quote_no: z.string().nullable(),
  /** sent, accepted or closed. */
  status: z.string(),
  /** Null on a dealer's quotation. */
  total: decimal.nullable(),
  sent_at: isoDateTime.nullable(),
  valid_until: z.string().nullable(),
  /** The page the farmer was sent; null on a dealer's quotation. */
  link: z.string().nullable(),
});
export type PortalQuotationWire = z.input<typeof quotationWireSchema>;

export const portalQuotationsSchema = z
  .object({ data: z.array(quotationWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({
      number: row.quote_no,
      status: row.status,
      total: row.total,
      sentAt: row.sent_at,
      validUntil: row.valid_until,
      link: row.link,
    })),
  );
export type PortalQuotation = z.output<typeof portalQuotationsSchema>[number];

const orderWireSchema = z.object({
  order_no: z.string(),
  /** in_progress, being_revised, dispatched, closed or cancelled. */
  status: z.string(),
  /** Null on a dealer's order. */
  total: decimal.nullable(),
  submitted_at: isoDateTime.nullable(),
  dispatches: z.array(z.object({ dc_no: z.string().nullable(), dispatched_at: isoDateTime })),
});
export type PortalOrderWire = z.input<typeof orderWireSchema>;

export const portalOrdersSchema = z
  .object({ data: z.array(orderWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({
      number: row.order_no,
      status: row.status,
      total: row.total,
      submittedAt: row.submitted_at,
      dispatches: row.dispatches.map((dispatch) => ({
        dcNo: dispatch.dc_no,
        dispatchedAt: dispatch.dispatched_at,
      })),
    })),
  );
export type PortalOrder = z.output<typeof portalOrdersSchema>[number];

const complaintWireSchema = z.object({
  complaint_no: z.string(),
  /** in_progress or closed. */
  status: z.string(),
  raised_at: isoDateTime.nullable(),
});
export type PortalComplaintWire = z.input<typeof complaintWireSchema>;

export const portalComplaintsSchema = z
  .object({ data: z.array(complaintWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({ number: row.complaint_no, status: row.status, raisedAt: row.raised_at })),
  );
export type PortalComplaint = z.output<typeof portalComplaintsSchema>[number];

export const PORTAL_RATING_TARGETS = ["installation", "service"] as const;
export type PortalRatingTarget = (typeof PORTAL_RATING_TARGETS)[number];

const ratingWireSchema = z.object({
  target: z.enum(PORTAL_RATING_TARGETS),
  order_no: z.string().nullable(),
  complaint_no: z.string().nullable(),
  score: z.number().int().min(1).max(5),
  /** His own words; null when an officer recorded it for him. */
  comment: z.string().nullable(),
  /** portal: he rated it here; staff: an officer recorded it for him. */
  entered_via: z.enum(["portal", "staff"]),
  created_at: isoDateTime,
});
export type PortalRatingWire = z.input<typeof ratingWireSchema>;

/** A rating as the screens read it. */
export interface PortalRating {
  readonly target: PortalRatingTarget;
  readonly orderNo: string | null;
  readonly complaintNo: string | null;
  readonly score: number;
  readonly comment: string | null;
  readonly enteredVia: "portal" | "staff";
  readonly createdAt: string;
}

function ratingOf(row: z.output<typeof ratingWireSchema>): PortalRating {
  return {
    target: row.target,
    orderNo: row.order_no,
    complaintNo: row.complaint_no,
    score: row.score,
    comment: row.comment,
    enteredVia: row.entered_via,
    createdAt: row.created_at,
  };
}

export const portalRatingsSchema = z
  .object({ data: z.array(ratingWireSchema) })
  .transform(({ data }) => data.map(ratingOf));

export const portalRatingSchema = z
  .object({ data: ratingWireSchema })
  .transform(({ data }) => ratingOf(data));

export interface PortalRatingRequest {
  readonly target: PortalRatingTarget;
  readonly order_no?: string | null;
  readonly complaint_no?: string | null;
  readonly score: number;
  readonly comment?: string | null;
}
