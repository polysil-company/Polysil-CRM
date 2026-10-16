import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * Approvals contract (APPR-001), from the backend's `QueuePage`, `QueueRow`, `QueueDocument`,
 * `DecisionRequest` and `DecisionResult` (backend/docs/api/approvals.md). One inbox holds
 * sales orders and quotation discounts (FS-013) side by side.
 */

/** Orders, quotation discounts, and complaint refunds (CMPL-007). */
export const APPROVAL_DOC_TYPES = ["sales_order", "quotation", "complaint"] as const;
export type ApprovalDocType = (typeof APPROVAL_DOC_TYPES)[number];

/**
 * The documents with approval limits: an order's value, a quotation's discount, and a
 * complaint's refund (FS-015b, rupees, the order's three managers, then Accounts).
 */
export const THRESHOLD_DOC_TYPES = ["sales_order", "quotation", "complaint"] as const;
export type ThresholdDocType = (typeof THRESHOLD_DOC_TYPES)[number];

const isoDateTime = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

const queueRowWireSchema = z.object({
  step_id: z.string().min(1),
  seq: z.number().int().positive(),
  /** The role code the step waits on. */
  role: z.string().min(1),
  /** Nobody of the step's own role covers it; a higher manager may decide it. */
  stalled: z.boolean(),
  doc_type: z.enum(APPROVAL_DOC_TYPES),
  document: z.object({
    id: z.string().min(1),
    /** Null on a quotation: a draft has no number until it is sent. */
    number: z.string().min(1).nullable(),
    party_name: z.string(),
    total: decimal,
    is_provisional: z.boolean(),
    raised_by: z.object({ id: z.string().min(1), full_name: z.string() }).nullable(),
    raised_at: isoDateTime,
    /** A quotation row: the effective discount asked for, in percent. Null on an order. */
    discount_pct: decimal.nullish(),
    /** Why the approval was asked, as the asker wrote it (backend #49). Null when none given. */
    request_remark: z.string().nullish(),
  }),
  waiting_since: isoDateTime,
});

export type QueueRowWire = z.input<typeof queueRowWireSchema>;

const queueRowSchema = queueRowWireSchema.transform((wire) => ({
  stepId: wire.step_id,
  seq: wire.seq,
  role: wire.role,
  stalled: wire.stalled,
  docType: wire.doc_type,
  document: {
    id: wire.document.id,
    number: wire.document.number,
    partyName: wire.document.party_name.trim() || "Unnamed party",
    total: wire.document.total,
    isProvisional: wire.document.is_provisional,
    raisedBy:
      wire.document.raised_by === null
        ? null
        : { id: wire.document.raised_by.id, name: wire.document.raised_by.full_name.trim() },
    raisedAt: wire.document.raised_at,
    discountPct: wire.document.discount_pct ?? null,
    requestRemark: wire.document.request_remark?.trim() || null,
  },
  waitingSince: wire.waiting_since,
}));

export type QueueRow = z.output<typeof queueRowSchema>;

/** GET /approvals/pending — one row at a time, so one odd row never blanks the inbox. */
export const queuePageSchema = cursorPageSchema(queueRowSchema);
export type QueuePage = CursorPage<QueueRow>;
export type QueuePageWire = { data: QueueRowWire[]; meta: PageMetaWire };

/** Rows a page asks for; the backend allows up to 100. */
export const QUEUE_PAGE_SIZE = 25;

export interface QueueParams {
  /** Also every lower step in the user's area, to cover a manager on leave. */
  readonly includeBelow: boolean;
}

export const APPROVAL_DECISIONS = ["approve", "reject"] as const;
export type ApprovalDecision = (typeof APPROVAL_DECISIONS)[number];

/** POST /approvals/steps/{id}/decision. */
export interface DecisionRequest {
  readonly decision: ApprovalDecision;
  readonly remark: string | null;
}

/**
 * The decision answers with the document it decided — an order, a quotation or a complaint. The inbox
 * needs only which one, to refresh it; `doc_type` is on both.
 */
export const decisionResultSchema = z
  .object({
    data: z.looseObject({ doc_type: z.enum(APPROVAL_DOC_TYPES), id: z.string().min(1) }),
  })
  .transform(({ data }) => ({ docType: data.doc_type, id: data.id }));

export type DecisionResult = z.output<typeof decisionResultSchema>;

export const DECISION_REMARK_MAX_LENGTH = 1000;

/**
 * The decision dialog: a remark, required to reject and on an Accounts step. `missingRemark`
 * is what to say when a required remark is left empty; null when it is optional.
 */
export function decisionFormSchema(
  missingRemark: string | null,
): z.ZodType<{ remark: string }, { remark: string }> {
  return z.object({
    remark: z
      .string()
      .trim()
      .max(DECISION_REMARK_MAX_LENGTH, { message: "Keep the remark under 1,000 characters" })
      .refine((value) => missingRemark === null || value.length > 0, {
        message: missingRemark ?? "",
      }),
  });
}

export type DecisionForm = { remark: string };

// ── approval limits (APPR-002) ────────────────────────────────────────────────────

/** An order's limits are for the three managers; a quotation's discount for five roles. */
export const ORDER_LIMIT_ROLES = ["district_manager", "state_manager", "regional_manager"] as const;
export const DISCOUNT_LIMIT_ROLES = [
  "field_officer",
  "district_manager",
  "state_manager",
  "regional_manager",
  "admin_sales",
] as const;
export type LimitRole = (typeof DISCOUNT_LIMIT_ROLES)[number];

const thresholdWireSchema = z.object({
  /** Any document the backend has limits for; rows of one the screen doesn't know are left out. */
  doc_type: z.string().min(1),
  role: z.string().min(1),
  territory: z.object({ id: z.string().min(1), name: z.string(), level: z.string() }).nullable(),
  /** Null: no ceiling. Rupees including GST for an order, a percent for a discount. */
  max_amount: decimal.nullable(),
  unit: z.enum(["inr", "pct"]),
});

export type ThresholdWire = z.input<typeof thresholdWireSchema>;

export interface Threshold {
  readonly docType: ThresholdDocType;
  readonly role: string;
  readonly territory: { readonly id: string; readonly name: string; readonly level: string } | null;
  /** Null: no ceiling. */
  readonly maxAmount: string | null;
  readonly unit: "inr" | "pct";
}

/**
 * GET and PUT /approvals/thresholds both answer with every row. A row for a document the
 * screen doesn't know yet is left out rather than failing the page: the backend added refund
 * limits (`complaint`) after this screen was built, and that broke it.
 */
export const thresholdsResponseSchema = z
  .object({ data: z.array(thresholdWireSchema) })
  .transform(({ data }) =>
    data.flatMap((wire): Threshold[] => {
      const docType = THRESHOLD_DOC_TYPES.find((known) => known === wire.doc_type);
      return docType === undefined
        ? []
        : [
            {
              docType,
              role: wire.role,
              territory: wire.territory,
              maxAmount: wire.max_amount,
              unit: wire.unit,
            },
          ];
    }),
  );

/** PUT /approvals/thresholds — one role's limit, company-wide (`territory_id: null`) or for a territory. */
export interface ThresholdPutRequest {
  readonly doc_type: ThresholdDocType;
  readonly role: LimitRole;
  readonly territory_id: string | null;
  /** Null for no ceiling. */
  readonly max_amount: string | null;
}

/** The limit form: an amount, or no ceiling where the role may have none. */
export const limitFormSchema = z
  .object({
    unit: z.enum(["inr", "pct"]),
    noLimit: z.boolean(),
    amount: z.string().trim(),
  })
  .superRefine((form, ctx) => {
    if (form.noLimit) {
      return;
    }
    if (!/^\d+(\.\d{1,2})?$/.test(form.amount)) {
      ctx.addIssue({
        code: "custom",
        path: ["amount"],
        message: form.unit === "inr" ? "An amount in rupees, like 100000" : "A percent, like 12.5",
      });
      return;
    }
    const value = Number(form.amount);
    if (form.unit === "inr" && value <= 0) {
      ctx.addIssue({ code: "custom", path: ["amount"], message: "Above ₹0" });
    }
    if (form.unit === "pct" && value > 100) {
      ctx.addIssue({ code: "custom", path: ["amount"], message: "At most 100%" });
    }
  });
export type LimitForm = z.infer<typeof limitFormSchema>;
