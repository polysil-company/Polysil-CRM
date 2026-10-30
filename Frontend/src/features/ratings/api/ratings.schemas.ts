import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * RATE-001 … RATE-004 · Ratings (FS-043, `ratings-contract.md`, generated `ratings.md`).
 * Staff record a farmer's stars for an installation, a service visit or a product; a dealer's
 * user rates Polysil the same way; every dealer has a rating derived from how fast it pays and
 * how much it orders.
 */

export const RATING_TARGETS = ["installation", "service", "product"] as const;
export type RatingTarget = (typeof RATING_TARGETS)[number];

export const RATED_BY = ["customer", "dealer"] as const;
export type RatedBy = (typeof RATED_BY)[number];

export const RATING_SUMMARY_GROUPS = ["partner", "product", "target"] as const;
export type RatingSummaryGroup = (typeof RATING_SUMMARY_GROUPS)[number];

/** `max_score` for the "unhappy customers" view: ratings of 1 or 2. */
export const LOW_RATING_MAX = 2;
export const RATING_COMMENT_MAX = 1000;
export const RATING_PAGE_SIZE = 50;

const id = z.string().min(1);
const isoDateTime = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

const docSchema = z.object({ id, number: z.string().nullable(), status: z.string() });

const ratingWireSchema = z.object({
  id,
  target: z.enum(RATING_TARGETS),
  score: z.number().int().min(1).max(5),
  /** Null for a dealer reading a customer's rating, or when none was given. */
  comment: z.string().nullable(),
  rated_by: z.enum(RATED_BY),
  /** Null for a dealer reading a customer's rating, and for one the farmer entered himself. */
  entered_by: z.object({ id, full_name: z.string() }).nullable(),
  entered_via: z.string().nullish(),
  partner: z.object({ id, name: z.string(), partner_type: z.string() }).nullable(),
  lead: z.object({ id, inquiry_no: z.string().nullable() }).nullable(),
  order: docSchema.nullable(),
  complaint: docSchema.nullable(),
  product: z.object({ id, description: z.string() }).nullable(),
  created_at: isoDateTime,
});
export type RatingWire = z.input<typeof ratingWireSchema>;

export const ratingSchema = ratingWireSchema.transform((wire) => ({
  id: wire.id,
  target: wire.target,
  score: wire.score,
  comment: wire.comment?.trim() || null,
  ratedBy: wire.rated_by,
  enteredBy:
    wire.entered_by === null ? null : { id: wire.entered_by.id, name: wire.entered_by.full_name },
  /** "portal": the farmer rated it himself. */
  enteredVia: wire.entered_via ?? null,
  partner: wire.partner === null ? null : { id: wire.partner.id, name: wire.partner.name },
  lead: wire.lead === null ? null : { id: wire.lead.id, code: wire.lead.inquiry_no },
  order: wire.order,
  complaint: wire.complaint,
  product: wire.product === null ? null : { id: wire.product.id, name: wire.product.description },
  createdAt: wire.created_at,
}));
export type Rating = z.output<typeof ratingSchema>;

export const ratingEnvelopeSchema = z.object({ data: ratingSchema }).transform((body) => body.data);

export const ratingPageSchema = cursorPageSchema(ratingSchema);
export type RatingPage = CursorPage<Rating>;
export type RatingPageWire = { data: RatingWire[]; meta: PageMetaWire };

/** The list's filters, as the page and the record cards ask for them. */
export interface RatingListParams {
  readonly target: RatingTarget | null;
  readonly salesOrderId: string | null;
  readonly complaintId: string | null;
  readonly partnerId: string | null;
  /** 2 shows the low ones. */
  readonly maxScore: number | null;
}

export interface RatingCreateRequest {
  readonly target: RatingTarget;
  readonly sales_order_id?: string | null;
  readonly complaint_id?: string | null;
  readonly product_id?: string | null;
  readonly score: number;
  readonly comment?: string | null;
}

const summaryRowWireSchema = z.object({
  key: z.object({ id, name: z.string() }),
  count: z.number().int().nonnegative(),
  /** To two decimals. */
  average: decimal,
  /** Ratings of 1 or 2. */
  low: z.number().int().nonnegative(),
});
export type RatingSummaryRowWire = z.input<typeof summaryRowWireSchema>;

export const ratingSummarySchema = z
  .object({ data: z.array(summaryRowWireSchema) })
  .transform((body) =>
    body.data.map((row) => ({
      key: row.key,
      count: row.count,
      average: Number(row.average),
      low: row.low,
    })),
  );
export type RatingSummaryRow = z.output<typeof ratingSummarySchema>[number];

const dealerRatingWireSchema = z.object({
  partner_id: id,
  /** Today in India: it is worked out on every read. */
  on: z.iso.date(),
  window_days: z.number().int().positive(),
  orders: z.number().int().nonnegative(),
  paid_orders: z.number().int().nonnegative(),
  /** Value-weighted days from order to full payment; null when no order counts. */
  payment_days: decimal.nullable(),
  payment_score: z.number().int().min(1).max(5).nullable(),
  /** Taxable value, before GST. */
  order_value: decimal,
  value_score: z.number().int().min(1).max(5).nullable(),
  /** The mean of the two scores, one decimal. */
  rating: decimal.nullable(),
  feedback: z.object({ count: z.number().int().nonnegative(), average: decimal.nullable() }),
});
export type DealerRatingWire = z.input<typeof dealerRatingWireSchema>;

export const dealerRatingSchema = z
  .object({ data: dealerRatingWireSchema })
  .transform(({ data }) => ({
    partnerId: data.partner_id,
    on: data.on,
    windowDays: data.window_days,
    orders: data.orders,
    paidOrders: data.paid_orders,
    paymentDays: data.payment_days === null ? null : Number(data.payment_days),
    paymentScore: data.payment_score,
    orderValue: data.order_value,
    valueScore: data.value_score,
    rating: data.rating === null ? null : Number(data.rating),
    feedback: {
      count: data.feedback.count,
      average: data.feedback.average === null ? null : Number(data.feedback.average),
    },
  }));
export type DealerRating = z.output<typeof dealerRatingSchema>;
