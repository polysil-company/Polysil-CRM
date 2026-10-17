import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * ACCT-002 … ACCT-005 · Payments (FS-022; `backend/docs/handover/payments-contract.md`,
 * `docs/api/payments.md`). Accounts records money received against sales orders; a receipt can
 * pay several orders, or part of it can stay on the dealer's account. Nothing is collected
 * online. Money is a decimal string with at most two places.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const PAYMENT_MODES = ["neft", "upi", "cheque", "cash", "adjustment"] as const;
export type PaymentMode = (typeof PAYMENT_MODES)[number];

/** The modes that need a reference: the UTR, UPI or cheque number (422 ref_required). */
export const MODES_WITH_REFERENCE: readonly PaymentMode[] = ["neft", "upi", "cheque"];

export const ORDER_PAYMENT_STATUSES = [
  "not_applicable",
  "unpaid",
  "part_paid",
  "paid",
  "overpaid",
] as const;
export type OrderPaymentStatus = (typeof ORDER_PAYMENT_STATUSES)[number];

/** At most five planned instalments on an order. */
export const MAX_INSTALMENTS = 5;

const userRef = z
  .object({ id, full_name: z.string() })
  .transform((wire) => ({ id: wire.id, name: wire.full_name.trim() || "Unknown" }));

// ── the order's payments block ───────────────────────────────────────────────────

const instalmentSchema = z
  .object({
    seq: z.number().int(),
    due_on: isoDate,
    amount: decimal,
    note: z.string().nullable(),
    /** Received has reached this instalment, taken in due order. */
    covered: z.boolean(),
  })
  .transform((wire) => ({
    seq: wire.seq,
    dueOn: wire.due_on,
    amount: wire.amount,
    note: wire.note,
    covered: wire.covered,
  }));
export type Instalment = z.output<typeof instalmentSchema>;

const receiptSchema = z
  .object({
    payment_id: id,
    received_on: isoDate,
    mode: z.enum(PAYMENT_MODES),
    ref_no: z.string().nullable(),
    /** What this receipt put on this order. */
    amount: decimal,
    is_short_payment: z.boolean(),
  })
  .transform((wire) => ({
    paymentId: wire.payment_id,
    receivedOn: wire.received_on,
    mode: wire.mode,
    refNo: wire.ref_no,
    amount: wire.amount,
    shortPayment: wire.is_short_payment,
  }));
export type OrderReceipt = z.output<typeof receiptSchema>;

/** `payments` on GET /orders/{id}: null for a caller who may not see payments (hide it). */
export const orderPaymentsSchema = z
  .object({
    /** The order total less its applied scheme and reward benefits. */
    payable: decimal,
    received: decimal,
    balance: decimal,
    status: z.enum(ORDER_PAYMENT_STATUSES),
    overdue: z.boolean(),
    overdue_amount: decimal,
    schedule: z.array(instalmentSchema),
    receipts: z.array(receiptSchema),
  })
  .transform((wire) => ({
    payable: wire.payable,
    received: wire.received,
    balance: wire.balance,
    status: wire.status,
    overdue: wire.overdue,
    overdueAmount: wire.overdue_amount,
    schedule: wire.schedule,
    receipts: wire.receipts,
  }));
export type OrderPayments = z.output<typeof orderPaymentsSchema>;
export type OrderPaymentsWire = z.input<typeof orderPaymentsSchema>;

/** PUT /orders/{id}/payment-schedule answers the order's payments block. */
export const orderPaymentsResponseSchema = z
  .object({ data: orderPaymentsSchema })
  .transform(({ data }) => data);

export interface ScheduleRequest {
  readonly instalments: readonly {
    readonly due_on: string;
    readonly amount: string;
    readonly note: string | null;
  }[];
}

// ── payments (receipts) ──────────────────────────────────────────────────────────

const paymentWireSchema = z.object({
  id,
  /** Null: a direct (farmer) order's payment. */
  partner: z.object({ id, name: z.string() }).nullable(),
  mode: z.enum(PAYMENT_MODES),
  ref_no: z.string().nullable(),
  received_on: isoDate,
  amount: decimal,
  allocated: decimal,
  unallocated: decimal,
  is_short_payment: z.boolean(),
  /** Internal; null for a dealer. */
  remark: z.string().nullable(),
  entered_by: userRef.nullable(),
  entered_at: isoDateTime,
  voided: z
    .object({ at: isoDateTime, by: userRef.nullable(), reason: z.string().nullish() })
    .nullable(),
  allocations: z.array(
    z.object({
      sales_order: z.object({ id, order_no: z.string().nullable() }),
      amount: decimal,
      /** The order's balance now; null when the caller may not see the order. */
      order_balance: decimal.nullable(),
    }),
  ),
});
export type PaymentWire = z.input<typeof paymentWireSchema>;

export interface Payment {
  readonly id: string;
  readonly partner: { readonly id: string; readonly name: string } | null;
  readonly mode: PaymentMode;
  readonly refNo: string | null;
  readonly receivedOn: string;
  readonly amount: string;
  readonly allocated: string;
  readonly unallocated: string;
  readonly shortPayment: boolean;
  readonly remark: string | null;
  readonly enteredBy: { readonly id: string; readonly name: string } | null;
  readonly enteredAt: string;
  readonly voided: {
    readonly at: string;
    readonly by: { readonly id: string; readonly name: string } | null;
    readonly reason: string | null;
  } | null;
  readonly allocations: readonly {
    readonly order: { readonly id: string; readonly orderNo: string | null };
    readonly amount: string;
    readonly orderBalance: string | null;
  }[];
}

function toPayment(wire: z.output<typeof paymentWireSchema>): Payment {
  return {
    id: wire.id,
    partner: wire.partner,
    mode: wire.mode,
    refNo: wire.ref_no,
    receivedOn: wire.received_on,
    amount: wire.amount,
    allocated: wire.allocated,
    unallocated: wire.unallocated,
    shortPayment: wire.is_short_payment,
    remark: wire.remark,
    enteredBy: wire.entered_by,
    enteredAt: wire.entered_at,
    voided:
      wire.voided === null
        ? null
        : { at: wire.voided.at, by: wire.voided.by, reason: wire.voided.reason ?? null },
    allocations: wire.allocations.map((allocation) => ({
      order: { id: allocation.sales_order.id, orderNo: allocation.sales_order.order_no },
      amount: allocation.amount,
      orderBalance: allocation.order_balance,
    })),
  };
}

export const paymentResponseSchema = z
  .object({ data: paymentWireSchema })
  .transform(({ data }) => toPayment(data));

export const paymentPageSchema = z
  .object({ data: z.array(paymentWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toPayment), nextCursor: meta.nextCursor }));
export type PaymentPage = z.output<typeof paymentPageSchema>;

export interface PaymentListParams {
  readonly partnerId: string | null;
  readonly orderId: string | null;
  readonly includeVoided: boolean;
}

export interface AllocationRequest {
  readonly sales_order_id: string;
  readonly amount: string;
}

export interface RecordPaymentRequest {
  /** Null: a direct (farmer) order's payment, which must be allocated in full. */
  readonly partner_id: string | null;
  readonly mode: PaymentMode;
  readonly ref_no: string | null;
  readonly received_on: string;
  readonly amount: string;
  readonly is_short_payment: boolean;
  readonly remark: string | null;
  readonly allocations: readonly AllocationRequest[];
}

// ── the dealer: credit and ledger (ACCT-005) ─────────────────────────────────────

export const LEDGER_ROW_KINDS = ["order", "benefit", "receipt"] as const;

const ledgerSchema = z.object({
  data: z.object({
    partner: z.object({ id, name: z.string() }),
    from: isoDate.nullable(),
    to: isoDate.nullable(),
    opening_balance: decimal,
    rows: z.array(
      z.object({
        on: isoDate,
        kind: z.enum(LEDGER_ROW_KINDS),
        ref: z.string(),
        debit: decimal.nullable(),
        credit: decimal.nullable(),
        /** Positive: the dealer owes. Negative: the dealer's credit. */
        balance: decimal,
      }),
    ),
    closing_balance: decimal,
    /** Live receipts not yet spread over orders. Information only. */
    unallocated: decimal,
  }),
});
export type PartnerLedgerWire = z.input<typeof ledgerSchema>["data"];

export const partnerLedgerSchema = ledgerSchema.transform(({ data }) => ({
  partner: data.partner,
  from: data.from,
  to: data.to,
  openingBalance: data.opening_balance,
  rows: data.rows,
  closingBalance: data.closing_balance,
  unallocated: data.unallocated,
}));
export type PartnerLedger = z.output<typeof partnerLedgerSchema>;

const creditSchema = z.object({
  data: z.object({
    partner_id: id,
    /** Null: no limit is set, and the dealer is never checked. */
    credit_limit: decimal.nullable(),
    /** Owed on open orders less live receipts. Negative: in credit. */
    exposure: decimal,
    /** Limit less exposure; null without a limit. Negative: over the limit. */
    available: decimal.nullable(),
    /** The company setting dealer_credit_check. */
    check: z.string(),
  }),
});
export type PartnerCreditWire = z.input<typeof creditSchema>["data"];

export const partnerCreditSchema = creditSchema.transform(({ data }) => ({
  partnerId: data.partner_id,
  creditLimit: data.credit_limit,
  exposure: data.exposure,
  available: data.available,
  check: data.check,
}));
export type PartnerCredit = z.output<typeof partnerCreditSchema>;
