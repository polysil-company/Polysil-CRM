import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  orderPaymentsResponseSchema,
  partnerCreditSchema,
  partnerLedgerSchema,
  paymentPageSchema,
  paymentResponseSchema,
  type AllocationRequest,
  type OrderPayments,
  type PartnerCredit,
  type PartnerLedger,
  type Payment,
  type PaymentListParams,
  type PaymentPage,
  type RecordPaymentRequest,
  type ScheduleRequest,
} from "./payments.schemas";

const log = createLogger({ file: "features/payments/api/payments.api.ts", dataId: "ACCT-002" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/**
 * ACCT-002 · Record money received, spread over the dealer's orders (or a direct order's, in
 * full). 422 ref_required, over_allocated, must_allocate, partner_mismatch; 409
 * order_not_payable, duplicate_reference.
 */
export function recordPayment({
  body,
  idempotencyKey,
}: WriteInput<RecordPaymentRequest>): Promise<Payment> {
  return apiRequest({
    dataId: "ACCT-002",
    logger: log,
    fn: "recordPayment",
    method: "POST",
    path: "/payments",
    body,
    idempotencyKey,
    schema: paymentResponseSchema,
  });
}

/** ACCT-003 · Receipts in your scope, newest first. */
export function listPayments(
  params: PaymentListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<PaymentPage> {
  return apiRequest({
    dataId: "ACCT-003",
    logger: log,
    fn: "listPayments",
    path: "/payments",
    query: {
      partner_id: params.partnerId ?? undefined,
      sales_order_id: params.orderId ?? undefined,
      include_voided: params.includeVoided ? "true" : undefined,
      cursor: params.cursor ?? undefined,
    },
    schema: paymentPageSchema,
    signal,
  });
}

/** ACCT-003 · One receipt. */
export function getPayment(paymentId: string, signal?: AbortSignal): Promise<Payment> {
  return apiRequest({
    dataId: "ACCT-003",
    logger: log,
    fn: "getPayment",
    path: `/payments/${encodeURIComponent(paymentId)}`,
    schema: paymentResponseSchema,
    signal,
  });
}

/** ACCT-003 · Spread what is left of a receipt over more orders. */
export function allocatePayment(
  paymentId: string,
  { body, idempotencyKey }: WriteInput<{ readonly allocations: readonly AllocationRequest[] }>,
): Promise<Payment> {
  return apiRequest({
    dataId: "ACCT-003",
    logger: log,
    fn: "allocatePayment",
    method: "POST",
    path: `/payments/${encodeURIComponent(paymentId)}/allocations`,
    body,
    idempotencyKey,
    schema: paymentResponseSchema,
  });
}

/** ACCT-003 · Void a mistaken receipt, with a reason; it is re-entered, never edited. */
export function voidPayment(
  paymentId: string,
  { body, idempotencyKey }: WriteInput<{ readonly reason: string }>,
): Promise<Payment> {
  return apiRequest({
    dataId: "ACCT-003",
    logger: log,
    fn: "voidPayment",
    method: "POST",
    path: `/payments/${encodeURIComponent(paymentId)}/void`,
    body,
    idempotencyKey,
    schema: paymentResponseSchema,
  });
}

/** ACCT-004 · Replace an order's instalment plan (0 to 5); answers its payments block. */
export function putPaymentSchedule(
  orderId: string,
  { body, idempotencyKey }: WriteInput<ScheduleRequest>,
): Promise<OrderPayments> {
  return apiRequest({
    dataId: "ACCT-004",
    logger: log,
    fn: "putPaymentSchedule",
    method: "PUT",
    path: `/orders/${encodeURIComponent(orderId)}/payment-schedule`,
    body,
    idempotencyKey,
    schema: orderPaymentsResponseSchema,
  });
}

/** ACCT-005 · A dealer's ledger: orders, benefits and receipts with a running balance. */
export function getPartnerLedger(
  partnerId: string,
  range: { readonly from: string | null; readonly to: string | null },
  signal?: AbortSignal,
): Promise<PartnerLedger> {
  return apiRequest({
    dataId: "ACCT-005",
    logger: log,
    fn: "getPartnerLedger",
    path: `/partners/${encodeURIComponent(partnerId)}/ledger`,
    query: { from: range.from ?? undefined, to: range.to ?? undefined },
    schema: partnerLedgerSchema,
    signal,
  });
}

/** ACCT-005 · A dealer's credit limit, exposure and what is left. 403 for partners and officers. */
export function getPartnerCredit(partnerId: string, signal?: AbortSignal): Promise<PartnerCredit> {
  return apiRequest({
    dataId: "ACCT-005",
    logger: log,
    fn: "getPartnerCredit",
    path: `/partners/${encodeURIComponent(partnerId)}/credit`,
    schema: partnerCreditSchema,
    signal,
  });
}
