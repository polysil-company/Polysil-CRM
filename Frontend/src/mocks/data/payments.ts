import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { PaymentWire } from "@/features/payments/api/payments.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import { mockUuid } from "./reference";

/** The mock's own id space for receipts. */
const PAYMENT_SPACE = 0xa7;

export function mockPaymentId(index: number): string {
  return mockUuid(PAYMENT_SPACE, index);
}

export interface MockInstalment {
  readonly due_on: string;
  readonly amount: string;
  readonly note: string | null;
}

const ACCOUNTS = { id: "usr-accounts", full_name: "Kavita Joshi" };

function rupees(value: number): string {
  return value.toFixed(2);
}

/**
 * Receipts for the seeded orders that can be paid: a part payment and an advance left on the
 * dealer's account, a full UPI payment, a direct order paid in cash, and one voided mistake.
 */
export function seedPayments(orders: readonly OrderWire[], now: Date = new Date()): PaymentWire[] {
  const today = todayInIndia(now);
  const day = (days: number): string => shiftCalendarDay(today, days);
  const at = (days: number): string => `${day(days)}T07:00:00.000Z`;
  const payable = (order: OrderWire): number => Number(order.payable ?? order.totals.total);
  const approved = orders.find(
    (order) => order.status === "approved" && order.partner?.partner_type === "dealer",
  );
  const shipped = orders.find(
    (order) => order.status === "partially_dispatched" && order.partner !== null,
  );
  const direct = orders.find((order) => order.status === "dispatched" && order.partner === null);
  const rows: PaymentWire[] = [];
  const base = {
    is_short_payment: false,
    remark: null,
    entered_by: ACCOUNTS,
    voided: null,
  };
  if (approved?.partner) {
    const part = Math.round(payable(approved) * 0.5);
    rows.push({
      ...base,
      id: mockPaymentId(1),
      partner: { id: approved.partner.id, name: approved.partner.name ?? "" },
      mode: "neft",
      ref_no: "UTR 4411 0098",
      received_on: day(-6),
      amount: rupees(part + 5000),
      allocated: rupees(part),
      unallocated: rupees(5000),
      remark: "Advance against the order; the rest stays on account.",
      entered_at: at(-6),
      allocations: [
        {
          sales_order: { id: approved.id, order_no: approved.order_no },
          amount: rupees(part),
          order_balance: null,
        },
      ],
    });
  }
  if (shipped?.partner) {
    rows.push({
      ...base,
      id: mockPaymentId(2),
      partner: { id: shipped.partner.id, name: shipped.partner.name ?? "" },
      mode: "upi",
      ref_no: "UPI 3328 7741 0021",
      received_on: day(-12),
      amount: rupees(payable(shipped)),
      allocated: rupees(payable(shipped)),
      unallocated: "0.00",
      entered_at: at(-12),
      allocations: [
        {
          sales_order: { id: shipped.id, order_no: shipped.order_no },
          amount: rupees(payable(shipped)),
          order_balance: null,
        },
      ],
    });
    rows.push({
      ...base,
      id: mockPaymentId(3),
      partner: { id: shipped.partner.id, name: shipped.partner.name ?? "" },
      mode: "cheque",
      ref_no: "CHQ 004512",
      received_on: day(-14),
      amount: rupees(payable(shipped)),
      allocated: "0.00",
      unallocated: "0.00",
      remark: "Entered twice by mistake.",
      entered_at: at(-14),
      voided: {
        at: at(-13),
        by: ACCOUNTS,
        reason: "Entered twice; the UPI receipt is the real one.",
      },
      allocations: [],
    });
  }
  if (direct !== undefined) {
    rows.push({
      ...base,
      id: mockPaymentId(4),
      partner: null,
      mode: "cash",
      ref_no: null,
      received_on: day(-20),
      amount: rupees(payable(direct)),
      allocated: rupees(payable(direct)),
      unallocated: "0.00",
      entered_at: at(-20),
      allocations: [
        {
          sales_order: { id: direct.id, order_no: direct.order_no },
          amount: rupees(payable(direct)),
          order_balance: null,
        },
      ],
    });
  }
  // Newest first.
  return rows.sort((left, right) => right.entered_at.localeCompare(left.entered_at));
}

/** An advance and a balance on the approved dealer order: the first is overdue in part. */
export function seedSchedules(
  orders: readonly OrderWire[],
  now: Date = new Date(),
): Map<string, MockInstalment[]> {
  const today = todayInIndia(now);
  const approved = orders.find(
    (order) => order.status === "approved" && order.partner?.partner_type === "dealer",
  );
  const schedules = new Map<string, MockInstalment[]>();
  if (approved !== undefined) {
    const total = Number(approved.payable ?? approved.totals.total);
    const advance = Math.round(total * 0.6);
    schedules.set(approved.id, [
      { due_on: shiftCalendarDay(today, -3), amount: rupees(advance), note: "Advance" },
      { due_on: shiftCalendarDay(today, 27), amount: rupees(total - advance), note: "Balance" },
    ]);
  }
  return schedules;
}
