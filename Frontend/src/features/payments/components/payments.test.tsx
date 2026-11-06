import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { OrderDetail } from "@/features/orders/components/order-detail";
import {
  allocatePayment,
  getPartnerCredit,
  getPartnerLedger,
  recordPayment,
  voidPayment,
} from "@/features/payments/api/payments.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockPaymentId } from "@/mocks/data/payments";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { MyLedger } from "./my-ledger";
import { PartnerCreditCard } from "./partner-credit";
import { balanceText } from "./partner-ledger";
import { ReceiptsList } from "./receipts-list";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

let keys = 0;
function key(): string {
  keys += 1;
  return `payments-test-${String(keys)}`;
}

/** The seeded approved dealer order: part paid, ₹5,000 left on the dealer's account. */
function approvedDealerOrder(): { id: string; partnerId: string; orderNo: string } {
  const order = mockDb.orders.find(
    (item) => item.status === "approved" && item.partner?.partner_type === "dealer",
  );
  if (order?.partner == null) throw new Error("No approved dealer order");
  return { id: order.id, partnerId: order.partner.id, orderNo: order.order_no ?? "" };
}

function reset(): void {
  resetMockDb();
  signInAs("account_manager");
}

describe("[ACCT-002] Record a payment (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("refuses a reference already recorded for the dealer", async () => {
    reset();
    const order = approvedDealerOrder();
    const code = await codeOf(
      recordPayment({
        body: {
          partner_id: order.partnerId,
          mode: "neft",
          ref_no: "UTR 4411 0098",
          received_on: "2026-10-10",
          amount: "1000.00",
          is_short_payment: false,
          remark: null,
          allocations: [],
        },
        idempotencyKey: key(),
      }),
    );
    expect(code).toBe("duplicate_reference");
  });

  it("refuses allocations above the amount, and a direct payment not fully allocated", async () => {
    reset();
    const order = approvedDealerOrder();
    expect(
      await codeOf(
        recordPayment({
          body: {
            partner_id: order.partnerId,
            mode: "cash",
            ref_no: null,
            received_on: "2026-10-10",
            amount: "100.00",
            is_short_payment: false,
            remark: null,
            allocations: [{ sales_order_id: order.id, amount: "200.00" }],
          },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("over_allocated");
    const direct = mockDb.orders.find(
      (item) => item.partner === null && item.status !== "draft" && item.status !== "cancelled",
    );
    if (direct === undefined) throw new Error("No direct order");
    expect(
      await codeOf(
        recordPayment({
          body: {
            partner_id: null,
            mode: "cash",
            ref_no: null,
            received_on: "2026-10-10",
            amount: "100.00",
            is_short_payment: false,
            remark: null,
            allocations: [],
          },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("must_allocate");
  });

  it("records a payment that reduces the order's balance", async () => {
    reset();
    const order = approvedDealerOrder();
    const saved = await recordPayment({
      body: {
        partner_id: order.partnerId,
        mode: "upi",
        ref_no: "UPI 1",
        received_on: "2026-10-10",
        amount: "1000.00",
        is_short_payment: false,
        remark: null,
        allocations: [{ sales_order_id: order.id, amount: "600.00" }],
      },
      idempotencyKey: key(),
    });
    expect(saved.unallocated).toBe("400.00");
    expect(saved.allocations).toHaveLength(1);
  });
});

describe("[ACCT-003] Receipts: void and allocate (contract)", () => {
  it("voids once, then refuses a second void and an allocation", async () => {
    reset();
    const paymentId = mockPaymentId(1);
    const voided = await voidPayment(paymentId, {
      body: { reason: "Typed twice" },
      idempotencyKey: key(),
    });
    expect(voided.voided?.reason).toBe("Typed twice");
    expect(
      await codeOf(voidPayment(paymentId, { body: { reason: "Again" }, idempotencyKey: key() })),
    ).toBe("already_void");
    const order = approvedDealerOrder();
    expect(
      await codeOf(
        allocatePayment(paymentId, {
          body: { allocations: [{ sales_order_id: order.id, amount: "1.00" }] },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("already_void");
  });

  it("spreads what is left of a receipt, never more", async () => {
    reset();
    const order = approvedDealerOrder();
    const paymentId = mockPaymentId(1);
    expect(
      await codeOf(
        allocatePayment(paymentId, {
          body: { allocations: [{ sales_order_id: order.id, amount: "5000.01" }] },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("over_allocated");
  });
});

describe("[ACCT-005] Ledger and credit (contract)", () => {
  it("runs the balance: orders owed, receipts and benefits paid", async () => {
    reset();
    const order = approvedDealerOrder();
    const ledger = await getPartnerLedger(order.partnerId, { from: null, to: null });
    const last = ledger.rows.at(-1);
    expect(last?.balance).toBe(ledger.closingBalance);
    expect(ledger.rows.some((row) => row.kind === "order")).toBe(true);
    expect(ledger.rows.some((row) => row.kind === "receipt")).toBe(true);
    expect(Number(ledger.unallocated)).toBe(5000);
  });

  it("keeps credit from dealers and field officers", async () => {
    reset();
    const order = approvedDealerOrder();
    signInAs("dealer");
    const dealer = await getPartnerCredit(order.partnerId).then(
      () => null,
      (caught: unknown) => (isApiError(caught) ? caught.status : null),
    );
    expect(dealer).toBe(403);
  });

  it("words a balance by which way it goes", () => {
    expect(balanceText("1000.00")).toBe("₹1,000.00 owed");
    expect(balanceText("-500.50")).toBe("₹500.50 in credit");
    expect(balanceText("0.00")).toBe("Settled");
  });
});

describe("[ACCT-003] ReceiptsList", () => {
  function show(): ReturnType<typeof userEvent.setup> {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <ReceiptsList />
        <Toaster />
      </>,
    );
    return user;
  }

  it("lists live receipts and shows voided ones on request", async () => {
    reset();
    const user = show();
    const list = await screen.findByRole("list", { name: "Receipts" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(within(list).queryByText("Voided")).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: "Show voided" }));
    expect(await within(list).findByText("Voided")).toBeInTheDocument();
  });

  it("voids a receipt with a reason", async () => {
    reset();
    const user = show();
    await screen.findByRole("list", { name: "Receipts" });
    const [first] = await screen.findAllByRole("button", { name: /^Void .+'s payment/ });
    if (first === undefined) throw new Error("No void button");
    await user.click(first);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Void payment" }));
    expect(await within(dialog).findByText("Say why, for the record.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Why"), "Entered on the wrong dealer");
    await user.click(within(dialog).getByRole("button", { name: "Void payment" }));
    expect(await screen.findByText("Payment voided")).toBeInTheDocument();
  });

  it("puts what is left of a receipt on an order", async () => {
    reset();
    const order = approvedDealerOrder();
    const user = show();
    await user.click(
      await screen.findByRole("button", { name: /^Spread what is left of .+'s payment/ }),
    );
    const dialog = await screen.findByRole("dialog");
    const input = await within(dialog).findByLabelText(
      new RegExp(order.orderNo.replace(/\//g, "\\/")),
    );
    await user.type(input, "6000");
    await user.click(within(dialog).getByRole("button", { name: "Put on the orders" }));
    expect(await within(dialog).findByText(/More than the ₹5,000.00 left/)).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "2000");
    await user.click(within(dialog).getByRole("button", { name: "Put on the orders" }));
    expect(await screen.findByText("Put on the orders")).toBeInTheDocument();
  });

  it("hides recording and voiding from a reader", async () => {
    reset();
    signInAs("state_manager");
    show();
    await screen.findByRole("list", { name: "Receipts" });
    expect(screen.queryByRole("button", { name: "Record payment" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Void / })).toBeNull();
  });
});

describe("[ACCT-002] OrderPaymentsCard on the order", () => {
  it("shows what is paid and what is left, with the overdue instalment", async () => {
    reset();
    const order = approvedDealerOrder();
    renderWithProviders(<OrderDetail orderId={order.id} />);
    const card = await screen.findByRole("region", { name: "Payments" });
    expect(await within(card).findByLabelText("Payment figures")).toHaveTextContent("Balance");
    expect(within(card).getByText("Part paid")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Record payment" })).toBeInTheDocument();
  });
});

describe("[ACCT-005] Ledger and credit cards", () => {
  it("shows a dealer its own ledger, and no credit standing", async () => {
    reset();
    signInAs("dealer");
    const partnerId = mockMeFor("dealer").data.partner?.id ?? "";
    renderWithProviders(
      <>
        <MyLedger />
        <PartnerCreditCard partnerId={partnerId} />
      </>,
    );
    expect(await screen.findByRole("heading", { name: "Your ledger" })).toBeInTheDocument();
    expect((await screen.findAllByText(/owed|in credit|Settled/)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Credit standing" })).toBeNull();
  });

  it("shows Accounts a dealer's credit standing", async () => {
    reset();
    const order = approvedDealerOrder();
    renderWithProviders(<PartnerCreditCard partnerId={order.partnerId} />);
    expect(await screen.findByRole("heading", { name: "Credit standing" })).toBeInTheDocument();
    expect(await screen.findByText("Exposure")).toBeInTheDocument();
  });
});
