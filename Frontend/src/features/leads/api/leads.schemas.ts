import { z } from "zod";

import { normalizeIndianMobile } from "@/lib/format";

/**
 * Leads contract (LEAD-001 … LEAD-004). Mock data and MSW handlers are
 * validated against these same schemas, so mocks cannot drift from the contract.
 *
 * TODO(LEAD-001): confirm field names, money unit and pagination shape with the
 * backend developer; update here first, then the mocks follow automatically.
 */

export const LEAD_STATUSES = [
  "new",
  "contacted",
  "qualified",
  "quoted",
  "negotiation",
  "won",
  "lost",
] as const;
export type LeadStatus = (typeof LEAD_STATUSES)[number];

/** The six capture sources agreed with the client. */
export const LEAD_SOURCES = [
  "whatsapp",
  "website",
  "employee",
  "qr_code",
  "phone_email",
  "offline",
] as const;
export type LeadSource = (typeof LEAD_SOURCES)[number];

export const ORDER_TYPES = [
  "subsidised",
  "commercial",
  "industrial",
  "export",
  "complaint",
] as const;
export type OrderType = (typeof ORDER_TYPES)[number];

const isoDateTime = z.iso.datetime({ offset: true });

export const leadSchema = z.object({
  id: z.string().min(1),
  /** Human reference, e.g. "LD-26-10042". */
  code: z.string().min(1),
  customerName: z.string().min(1),
  phone: z.string().min(1),
  village: z.string().nullable(),
  district: z.string().min(1),
  state: z.string().min(1),
  source: z.enum(LEAD_SOURCES),
  type: z.enum(ORDER_TYPES),
  status: z.enum(LEAD_STATUSES),
  /** Rupees. */
  estimatedValue: z.number().nonnegative().nullable(),
  winProbability: z.number().int().min(0).max(100),
  crops: z.array(z.string().min(1)),
  acreage: z.number().nonnegative().nullable(),
  owner: z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    avatarUrl: z.url().nullable(),
  }),
  /** The channel partner who brought the lead — receives it if the owner leaves. */
  channelPartner: z.object({ id: z.string().min(1), name: z.string().min(1) }).nullable(),
  /** Interactions per week, oldest first. */
  engagement: z.array(z.number().int().nonnegative()),
  followUpAt: isoDateTime.nullable(),
  lastActivityAt: isoDateTime.nullable(),
  lostReason: z.string().nullable(),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
});

export type Lead = z.infer<typeof leadSchema>;

export const LEAD_SORT_FIELDS = [
  "createdAt",
  "customerName",
  "estimatedValue",
  "followUpAt",
  "winProbability",
] as const;
export type LeadSortField = (typeof LEAD_SORT_FIELDS)[number];

export const SORT_ORDERS = ["asc", "desc"] as const;
export type SortOrder = (typeof SORT_ORDERS)[number];

export const LEAD_PAGE_SIZES = [25, 50, 100] as const;

export interface LeadListParams {
  readonly page: number;
  readonly pageSize: number;
  readonly sort: LeadSortField;
  readonly order: SortOrder;
  readonly q: string;
  readonly status: readonly LeadStatus[];
  readonly source: readonly LeadSource[];
  readonly type: readonly OrderType[];
}

export const leadListResponseSchema = z.object({
  items: z.array(leadSchema),
  page: z.number().int().min(1),
  pageSize: z.number().int().min(1),
  total: z.number().int().nonnegative(),
});

export type LeadListResponse = z.infer<typeof leadListResponseSchema>;

const countSchema = z.number().int().nonnegative();

export const leadSummarySchema = z.object({
  total: countSchema,
  byStatus: z.record(z.enum(LEAD_STATUSES), countSchema),
  bySource: z.record(z.enum(LEAD_SOURCES), countSchema),
  byType: z.record(z.enum(ORDER_TYPES), countSchema),
  followUpsDueToday: countSchema,
});

export type LeadSummary = z.infer<typeof leadSummarySchema>;

/** POST /leads request body — what the backend receives. */
export const createLeadRequestSchema = z.object({
  customerName: z.string().min(2).max(120),
  phone: z.string().regex(/^\+91[6-9]\d{9}$/),
  village: z.string().max(80),
  district: z.string().min(2).max(80),
  state: z.string().min(2).max(80),
  source: z.enum(LEAD_SOURCES),
  type: z.enum(ORDER_TYPES),
  estimatedValue: z.number().nonnegative().nullable(),
  notes: z.string().max(500),
});

export type CreateLeadRequest = z.infer<typeof createLeadRequestSchema>;

const AMOUNT_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

/**
 * The New Lead form: what the user types (strings) → the request body.
 * Error messages are user-facing copy.
 */
export const createLeadFormSchema = z.object({
  customerName: z
    .string()
    .trim()
    .min(2, "Enter the customer's full name.")
    .max(120, "Keep the name under 120 characters."),
  phone: z
    .string()
    .trim()
    .refine(
      (value) => normalizeIndianMobile(value) !== null,
      "Enter a 10-digit Indian mobile number.",
    )
    .transform((value) => normalizeIndianMobile(value) ?? value),
  village: z.string().trim().max(80, "Keep the village under 80 characters."),
  district: z.string().trim().min(2, "Enter the district."),
  state: z.string().trim().min(2, "Enter the state."),
  source: z.enum(LEAD_SOURCES, "Choose where this lead came from."),
  type: z.enum(ORDER_TYPES, "Choose the order type."),
  estimatedValue: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || AMOUNT_PATTERN.test(value),
      "Enter an amount in rupees, e.g. 125000.",
    )
    .transform((value) => (value === "" ? null : Number(value))),
  notes: z.string().trim().max(500, "Keep notes under 500 characters."),
});

export type CreateLeadFormValues = z.input<typeof createLeadFormSchema>;
