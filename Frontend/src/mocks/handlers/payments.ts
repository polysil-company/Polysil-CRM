import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  MAX_INSTALMENTS,
  MODES_WITH_REFERENCE,
  PAYMENT_MODES,
  type OrderPaymentsWire,
  type PartnerLedgerWire,
  type PaymentWire,
} from "@/features/payments/api/payments.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPaymentId } from "@/mocks/data/payments";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * ACCT-002 … ACCT-005 · Payments (FS-022, `docs/api/payments.md`). Accounts (payments CEA)
 * records, allocates, voids and plans; managers read; a field officer sees nothing; a dealer
 * sees its own receipts without remarks.
 */

type Action = "view" | "create" | "edit" | "approve";

function allowed(action: Action): boolean {
  return can(mockPermissionsFor(readMockRole()), "payments", action);
}

/** A field officer's `payments` on an order is null; a dealer and every other staff role read. */
function seesPayments(): boolean {
  const role = readMockRole();
  return (
    role !== "employee" && (isPartnerRole(role) || allowed("view") || role.endsWith("manager"))
  );
}

function forbidden(): Response {
  return errorResponse(403, "forbidden", "Not in your permissions.");
}

function invalid(code: string, message: string, fields: Record<string, string>): Response {
  return errorResponse(422, code, message, fields);
}

function paise(value: string | number): number {
  return Math.round(Number(value) * 100);
}

function rupees(value: number): string {
  return (value / 100).toFixed(2);
}

const money = z
  .union([z.string(), z.number()])
  .transform((value) => String(value).trim())
  .refine((value) => /^\d+(\.\d{1,2})?$/.test(value), "Rupees, at most two decimal places.");

/** What the order owes: nothing once cancelled; otherwise its payable (benefits taken off). */
function payableOf(order: OrderWire): number {
  return order.status === "cancelled" ? 0 : paise(order.payable ?? order.totals.total);
}

function livePayments(): PaymentWire[] {
  return mockDb.payments.filter((payment) => payment.voided === null);
}

function receivedOn(orderId: string): number {
  return livePayments()
    .flatMap((payment) => payment.allocations)
    .filter((allocation) => allocation.sales_order.id === orderId)
    .reduce((sum, allocation) => sum + paise(allocation.amount), 0);
}

function notPayable(order: OrderWire): boolean {
  return order.status === "draft" || order.status === "cancelled" || payableOf(order) === 0;
}

/** The order's `payments` block, or null for a reader who may not see payments. */
export function paymentsBlockFor(order: OrderWire): OrderPaymentsWire | null {
  if (!seesPayments()) return null;
  const payable = payableOf(order);
  const received = receivedOn(order.id);
  const today = todayInIndia();
  let cumulative = 0;
  const schedule = (mockDb.paymentSchedules.get(order.id) ?? []).map((row, index) => {
    cumulative += paise(row.amount);
    return {
      seq: index + 1,
      due_on: row.due_on,
      amount: row.amount,
      note: row.note,
      covered: received >= cumulative,
    };
  });
  const dueByToday = schedule
    .filter((row) => row.due_on < today)
    .reduce((sum, row) => sum + paise(row.amount), 0);
  const overdueAmount = Math.max(0, dueByToday - received);
  const receipts = livePayments().flatMap((payment) =>
    payment.allocations
      .filter((allocation) => allocation.sales_order.id === order.id)
      .map((allocation) => ({
        payment_id: payment.id,
        received_on: payment.received_on,
        mode: payment.mode,
        ref_no: payment.ref_no,
        amount: allocation.amount,
        is_short_payment: payment.is_short_payment,
      })),
  );
  const status = notPayable(order)
    ? "not_applicable"
    : received === 0
      ? "unpaid"
      : received < payable
        ? "part_paid"
        : received === payable
          ? "paid"
          : "overpaid";
  return {
    payable: rupees(payable),
    received: rupees(received),
    balance: rupees(payable - received),
    status,
    overdue: overdueAmount > 0,
    overdue_amount: rupees(overdueAmount),
    schedule,
    receipts,
  };
}

/** What the caller reads of a receipt: a dealer gets its own, without the remark. */
function forReader(payment: PaymentWire): PaymentWire {
  const withBalances = {
    ...payment,
    allocations: payment.allocations.map((allocation) => {
      const order = mockDb.orders.find((item) => item.id === allocation.sales_order.id);
      return {
        ...allocation,
        order_balance: order === undefined ? null : rupees(payableOf(order) - receivedOn(order.id)),
      };
    }),
  };
  return isPartnerRole(readMockRole()) ? { ...withBalances, remark: null } : withBalances;
}

function myPartnerId(): string | null {
  const role = readMockRole();
  return isPartnerRole(role) ? (mockMeFor(role).data.partner?.id ?? null) : null;
}

const allocationSchema = z.object({ sales_order_id: z.string().min(1), amount: money });

/** Checks allocations against the receipt's dealer and what is left; null when they're good. */
function allocationProblem(
  partnerId: string | null,
  allocations: readonly { sales_order_id: string; amount: string }[],
  available: number,
): Response | null {
  for (const [index, allocation] of allocations.entries()) {
    const order = mockDb.orders.find((item) => item.id === allocation.sales_order_id);
    if (order === undefined) {
      return invalid("validation_error", "Some fields need correcting.", {
        [`allocations[${String(index)}].sales_order_id`]: "No such order in your scope.",
      });
    }
    if (notPayable(order)) {
      return errorResponse(
        409,
        "order_not_payable",
        `${order.order_no ?? "A draft"} can't be paid.`,
      );
    }
    if (partnerId !== null && order.partner?.id !== partnerId) {
      return invalid("partner_mismatch", "An order belongs to another dealer.", {
        [`allocations[${String(index)}].sales_order_id`]: "Another dealer's order.",
      });
    }
    if (paise(allocation.amount) <= 0) {
      return invalid("validation_error", "Some fields need correcting.", {
        [`allocations[${String(index)}].amount`]: "More than 0.",
      });
    }
  }
  const total = allocations.reduce((sum, allocation) => sum + paise(allocation.amount), 0);
  if (total > available) {
    return invalid("over_allocated", "The amounts add up to more than the receipt.", {
      allocations: "More than the receipt.",
    });
  }
  return null;
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

function findPayment(paymentId: unknown): PaymentWire | Response {
  const found = mockDb.payments.find((payment) => payment.id === paymentId);
  return found ?? errorResponse(404, "not_found", "Not in your scope.");
}

function enteredBy(): { id: string; full_name: string } {
  const me = mockMeFor(readMockRole()).data;
  return { id: me.id, full_name: me.full_name };
}

export const paymentHandlers = [
  http.post(buildApiUrl("/payments"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create") || isPartnerRole(readMockRole())) return forbidden();
    const parsed = z
      .object({
        partner_id: z.string().min(1).nullable(),
        mode: z.enum(PAYMENT_MODES),
        ref_no: z.string().nullish(),
        received_on: z.iso.date({ message: "A date." }),
        amount: money,
        is_short_payment: z.boolean().default(false),
        remark: z.string().nullish(),
        allocations: z.array(allocationSchema).default([]),
      })
      .safeParse(await request.json());
    if (!parsed.success) {
      return invalid("validation_error", "Some fields need correcting.", fieldsOf(parsed.error));
    }
    const body = parsed.data;
    const ref = body.ref_no?.trim() ?? "";
    if (MODES_WITH_REFERENCE.includes(body.mode) && ref === "") {
      return invalid("ref_required", "This mode needs a reference.", {
        ref_no: "The UTR, UPI or cheque number.",
      });
    }
    if (paise(body.amount) <= 0) {
      return invalid("validation_error", "Some fields need correcting.", {
        amount: "More than 0.",
      });
    }
    const partner =
      body.partner_id === null ? null : mockDb.partners.find((item) => item.id === body.partner_id);
    if (partner === undefined) {
      return invalid("validation_error", "Some fields need correcting.", {
        partner_id: "No such dealer in your scope.",
      });
    }
    const problem = allocationProblem(body.partner_id, body.allocations, paise(body.amount));
    if (problem !== null) return problem;
    const allocated = body.allocations.reduce((sum, row) => sum + paise(row.amount), 0);
    if (partner === null && allocated !== paise(body.amount)) {
      return invalid("must_allocate", "A direct order's payment is allocated in full.", {
        allocations: "Allocate all of it.",
      });
    }
    if (
      ref !== "" &&
      livePayments().some(
        (payment) => payment.ref_no === ref && (payment.partner?.id ?? null) === body.partner_id,
      )
    ) {
      return errorResponse(409, "duplicate_reference", "This reference is already recorded.", {
        ref_no: "Already recorded for this dealer.",
      });
    }
    const payment: PaymentWire = {
      id: mockPaymentId(100 + mockDb.payments.length),
      partner: partner === null ? null : { id: partner.id, name: partner.name },
      mode: body.mode,
      ref_no: ref === "" ? null : ref,
      received_on: body.received_on,
      amount: rupees(paise(body.amount)),
      allocated: rupees(allocated),
      unallocated: rupees(paise(body.amount) - allocated),
      is_short_payment: body.is_short_payment,
      remark: body.remark?.trim() === "" ? null : (body.remark?.trim() ?? null),
      entered_by: enteredBy(),
      entered_at: new Date().toISOString(),
      voided: null,
      allocations: body.allocations.map((row) => {
        const order = mockDb.orders.find((item) => item.id === row.sales_order_id);
        return {
          sales_order: { id: row.sales_order_id, order_no: order?.order_no ?? null },
          amount: rupees(paise(row.amount)),
          order_balance: null,
        };
      }),
    };
    mockDb.payments.unshift(payment);
    return HttpResponse.json({ data: forReader(payment) }, { status: 201 });
  }),

  http.get(buildApiUrl("/payments"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPayments()) return forbidden();
    const url = new URL(request.url);
    const partnerId = url.searchParams.get("partner_id");
    const orderId = url.searchParams.get("sales_order_id");
    const withVoided = url.searchParams.get("include_voided") === "true";
    const mine = myPartnerId();
    const rows = mockDb.payments.filter(
      (payment) =>
        (withVoided || payment.voided === null) &&
        (mine === null || payment.partner?.id === mine) &&
        (partnerId === null || payment.partner?.id === partnerId) &&
        (orderId === null ||
          payment.allocations.some((allocation) => allocation.sales_order.id === orderId)),
    );
    return HttpResponse.json({ data: rows.map(forReader), meta: { limit: 50, next_cursor: null } });
  }),

  http.get(buildApiUrl("/payments/:paymentId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPayments()) return forbidden();
    const payment = findPayment(params.paymentId);
    return payment instanceof Response ? payment : HttpResponse.json({ data: forReader(payment) });
  }),

  http.post(buildApiUrl("/payments/:paymentId/allocations"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const payment = findPayment(params.paymentId);
    if (payment instanceof Response) return payment;
    if (payment.voided !== null) {
      return errorResponse(409, "already_void", "A voided receipt can't be allocated.");
    }
    const parsed = z
      .object({ allocations: z.array(allocationSchema).min(1, "At least one order.") })
      .safeParse(await request.json());
    if (!parsed.success) {
      return invalid("validation_error", "Some fields need correcting.", fieldsOf(parsed.error));
    }
    const problem = allocationProblem(
      payment.partner?.id ?? null,
      parsed.data.allocations,
      paise(payment.unallocated),
    );
    if (problem !== null) return problem;
    for (const row of parsed.data.allocations) {
      const order = mockDb.orders.find((item) => item.id === row.sales_order_id);
      const existing = payment.allocations.find(
        (allocation) => allocation.sales_order.id === row.sales_order_id,
      );
      if (existing !== undefined) {
        existing.amount = rupees(paise(existing.amount) + paise(row.amount));
      } else {
        payment.allocations.push({
          sales_order: { id: row.sales_order_id, order_no: order?.order_no ?? null },
          amount: rupees(paise(row.amount)),
          order_balance: null,
        });
      }
    }
    const allocated = payment.allocations.reduce((sum, row) => sum + paise(row.amount), 0);
    payment.allocated = rupees(allocated);
    payment.unallocated = rupees(paise(payment.amount) - allocated);
    return HttpResponse.json({ data: forReader(payment) });
  }),

  http.post(buildApiUrl("/payments/:paymentId/void"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const payment = findPayment(params.paymentId);
    if (payment instanceof Response) return payment;
    const parsed = z.object({ reason: z.string() }).safeParse(await request.json());
    const reason = parsed.success ? parsed.data.reason.trim() : "";
    if (reason === "") {
      return invalid("validation_error", "Some fields need correcting.", { reason: "Say why." });
    }
    if (payment.voided !== null) {
      return errorResponse(409, "already_void", "It is already voided.");
    }
    payment.voided = { at: new Date().toISOString(), by: enteredBy(), reason };
    return HttpResponse.json({ data: forReader(payment) });
  }),

  http.put(buildApiUrl("/orders/:orderId/payment-schedule"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const order = mockDb.orders.find((item) => item.id === params.orderId);
    if (order === undefined) return errorResponse(404, "not_found", "Not in your scope.");
    if (notPayable(order)) {
      return errorResponse(409, "order_not_payable", "This order can't be paid.");
    }
    const parsed = z
      .object({
        instalments: z
          .array(
            z.object({
              due_on: z.iso.date({ message: "A date." }),
              amount: money,
              note: z.string().nullish(),
            }),
          )
          .max(MAX_INSTALMENTS, `At most ${String(MAX_INSTALMENTS)}.`),
      })
      .safeParse(await request.json());
    if (!parsed.success) {
      return invalid("validation_error", "Some fields need correcting.", fieldsOf(parsed.error));
    }
    const rows = [...parsed.data.instalments].sort((left, right) =>
      left.due_on.localeCompare(right.due_on),
    );
    const zero = rows.findIndex((row) => paise(row.amount) <= 0);
    if (zero >= 0) {
      return invalid("validation_error", "Some fields need correcting.", {
        [`instalments[${String(zero)}].amount`]: "More than 0.",
      });
    }
    const total = rows.reduce((sum, row) => sum + paise(row.amount), 0);
    if (total > payableOf(order)) {
      return invalid("schedule_over_payable", "The instalments add up to more than the payable.", {
        instalments: "More than the payable.",
      });
    }
    mockDb.paymentSchedules.set(
      order.id,
      rows.map((row) => ({
        due_on: row.due_on,
        amount: rupees(paise(row.amount)),
        note: row.note?.trim() === "" ? null : (row.note?.trim() ?? null),
      })),
    );
    return HttpResponse.json({ data: paymentsBlockFor(order) });
  }),

  http.get(buildApiUrl("/partners/:partnerId/ledger"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPayments()) return forbidden();
    const partnerId = String(params.partnerId);
    const mine = myPartnerId();
    if (mine !== null && mine !== partnerId)
      return errorResponse(404, "not_found", "Not in your scope.");
    const partner = mockDb.partners.find((item) => item.id === partnerId);
    if (partner === undefined && mine === null) {
      return errorResponse(404, "not_found", "Not in your scope.");
    }
    const url = new URL(request.url);
    const from = url.searchParams.get("from");
    const to = url.searchParams.get("to");
    type Row = PartnerLedgerWire["rows"][number];
    const events: Omit<Row, "balance">[] = [
      ...mockDb.orders
        .filter(
          (order) =>
            order.partner?.id === partnerId &&
            order.approved_at !== null &&
            order.status !== "cancelled",
        )
        .flatMap((order) => {
          const on = order.approved_at?.slice(0, 10) ?? todayInIndia();
          return [
            {
              on,
              kind: "order" as const,
              ref: order.order_no ?? "Order",
              debit: order.totals.total,
              credit: null,
            },
            ...(order.benefits ?? [])
              .filter((benefit) => benefit.status === "applied")
              .map((benefit) => ({
                on: benefit.applied_at.slice(0, 10),
                kind: "benefit" as const,
                ref: `${benefit.kind === "reward_redemption" ? "Reward points" : "Scheme"} ${order.order_no ?? ""}`.trim(),
                debit: null,
                credit: benefit.amount,
              })),
          ];
        }),
      ...livePayments()
        .filter((payment) => payment.partner?.id === partnerId)
        .map((payment) => ({
          on: payment.received_on,
          kind: "receipt" as const,
          ref: `${payment.mode.toUpperCase()} ${payment.ref_no ?? ""}`.trim(),
          debit: null,
          credit: payment.amount,
        })),
    ].sort((left, right) => left.on.localeCompare(right.on));
    const move = (row: Omit<Row, "balance">): number =>
      paise(row.debit ?? "0") - paise(row.credit ?? "0");
    const opening = events
      .filter((row) => from !== null && row.on < from)
      .reduce((sum, row) => sum + move(row), 0);
    let running = opening;
    const rows: Row[] = events
      .filter((row) => (from === null || row.on >= from) && (to === null || row.on <= to))
      .map((row) => {
        running += move(row);
        return { ...row, balance: rupees(running) };
      });
    const unallocated = livePayments()
      .filter((payment) => payment.partner?.id === partnerId)
      .reduce((sum, payment) => sum + paise(payment.unallocated), 0);
    const ledger: PartnerLedgerWire = {
      partner: { id: partnerId, name: partner?.name ?? "" },
      from,
      to,
      opening_balance: rupees(opening),
      rows,
      closing_balance: rupees(running),
      unallocated: rupees(unallocated),
    };
    return HttpResponse.json({ data: ledger });
  }),

  http.get(buildApiUrl("/partners/:partnerId/credit"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const role = readMockRole();
    // Credit terms are never shown to partners or field officers.
    if (isPartnerRole(role) || role === "employee") return forbidden();
    const partner = mockDb.partners.find((item) => item.id === params.partnerId);
    if (partner === undefined) return errorResponse(404, "not_found", "Not in your scope.");
    const open = mockDb.orders.filter(
      (order) =>
        order.partner?.id === partner.id &&
        ["submitted", "approved", "partially_dispatched"].includes(order.status),
    );
    const owed = open.reduce((sum, order) => sum + payableOf(order), 0);
    const paid = livePayments()
      .filter((payment) => payment.partner?.id === partner.id)
      .reduce((sum, payment) => sum + paise(payment.amount), 0);
    const exposure = owed - paid;
    const limit = partner.credit_limit == null ? null : paise(partner.credit_limit);
    return HttpResponse.json({
      data: {
        partner_id: partner.id,
        credit_limit: limit === null ? null : rupees(limit),
        exposure: rupees(exposure),
        available: limit === null ? null : rupees(limit - exposure),
        check: "warn",
      },
    });
  }),
];
