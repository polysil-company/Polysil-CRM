import { afterEach, describe, expect, it } from "vitest";

import { decideApprovalStep, listPendingApprovals } from "@/features/approvals/api/approvals.api";
import { isApiError } from "@/lib/api/errors";
import { ROLES, type Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  cancelOrder,
  closeOrderShort,
  createDispatch,
  createOrder,
  deleteOrder,
  getOrder,
  getOrderTimeline,
  listOrders,
  patchOrder,
  submitOrder,
  voidDispatch,
} from "./orders.api";
import type { Order, OrderListParams } from "./orders.schemas";

let keys = 0;
function key(): string {
  keys += 1;
  return `orders-test-${String(keys)}`;
}

/** What the call was refused with, or a failure when it wasn't refused. */
async function refusal(call: Promise<unknown>): Promise<{ status: number; code: string | null }> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) {
      return { status: error.status ?? 0, code: error.code ?? null };
    }
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

const ALL: OrderListParams = {
  cursor: null,
  pageSize: 25,
  q: "",
  status: [],
  orderType: null,
  mine: false,
  leadId: null,
};

function seeded(status: Order["status"]): string {
  const order = mockDb.orders.find((item) => item.status === status);
  if (order === undefined) {
    throw new Error(`No ${status} order in the mock`);
  }
  return order.id;
}

/** An accepted, current quotation that no live order carries yet. */
function freeAcceptedQuotation(): string {
  const taken = new Set(
    mockDb.orders
      .filter((order) => order.status !== "cancelled")
      .flatMap((order) => order.quotations.map((quotation) => quotation.id)),
  );
  const quotation = mockDb.quotations.find(
    (item) => item.status === "accepted" && item.superseded_by === null && !taken.has(item.id),
  );
  if (quotation === undefined) {
    throw new Error("Every accepted quotation is on an order in the mock");
  }
  return quotation.id;
}

function as(role: Role): void {
  writeMockRole(role);
}

function reset(): void {
  resetMockDb();
  as("state_manager");
}

describe("[SO-001] listOrders", () => {
  afterEach(reset);

  it("lists newest first with the count, and filters by status, type and search", async () => {
    const page = await listOrders(ALL);
    expect(page.total).toBe(page.items.length);
    const times = page.items.map((order) => Date.parse(order.createdAt));
    expect([...times].sort((a, b) => b - a)).toEqual(times);

    const waiting = await listOrders({ ...ALL, status: ["submitted"] });
    expect(waiting.items.length).toBeGreaterThan(0);
    expect(
      waiting.items.every((order) => order.status === "submitted" && order.waitingOn !== null),
    ).toBe(true);

    const first = page.items[0];
    const found = await listOrders({ ...ALL, q: first?.orderNo ?? "" });
    expect(found.items.map((order) => order.id)).toEqual([first?.id]);

    const industrial = await listOrders({ ...ALL, orderType: "industrial" });
    expect(industrial.items.every((order) => order.orderType === "industrial")).toBe(true);
  });

  it("shows how much has shipped", async () => {
    const page = await listOrders({ ...ALL, status: ["dispatched", "partially_dispatched"] });
    const shares = page.items.map((order) => [order.status, order.dispatchedPct] as const);
    expect(shares).toContainEqual(["dispatched", 100]);
    expect(
      shares.some(([status, pct]) => status === "partially_dispatched" && pct > 0 && pct < 100),
    ).toBe(true);
  });
});

describe("[SO-002] getOrder", () => {
  afterEach(reset);

  it("reads the document with its lines, chain and dispatches, and its history", async () => {
    const order = await getOrder(seeded("partially_dispatched"));
    expect(order.approval?.status).toBe("approved");
    expect(order.approval?.steps.map((step) => step.role).slice(-2)).toEqual([
      "account_manager",
      "dispatch_manager",
    ]);
    expect(order.dispatches).toHaveLength(1);
    const line = order.lines[0];
    expect(Number(line?.qtyDispatched) + Number(line?.qtyOpen)).toBe(Number(line?.qty));

    const history = await getOrderTimeline({ orderId: order.id, cursor: null });
    expect(history.items.map((event) => event.kind)).toEqual(
      expect.arrayContaining([
        "order.created",
        "order.submitted",
        "order.approved",
        "dispatch.recorded",
      ]),
    );
  });

  it("answers 404 for an order that isn't there", async () => {
    await expect(refusal(getOrder("no-such-order"))).resolves.toEqual({
      status: 404,
      code: "not_found",
    });
  });
});

describe("[SO-003] createOrder, patchOrder, deleteOrder", () => {
  afterEach(reset);

  it("makes a draft from an accepted quotation, once", async () => {
    as("employee");
    const quotationId = freeAcceptedQuotation();
    const body = {
      order_type: "commercial" as const,
      quotation_ids: [quotationId],
      delivery_address: "Survey 12, Rajkot",
      payment_terms: "credit" as const,
      remarks: null,
    };
    const order = await createOrder({ body, idempotencyKey: key() });
    expect(order).toMatchObject({ status: "draft", orderNo: null, paymentTerms: "credit" });
    expect(order.quotations.map((quotation) => quotation.id)).toEqual([quotationId]);

    await expect(refusal(createOrder({ body, idempotencyKey: key() }))).resolves.toEqual({
      status: 409,
      code: "quotation_on_order",
    });
  });

  it("refuses a quotation that isn't accepted", async () => {
    const draft = mockDb.quotations.find((item) => item.status === "draft");
    await expect(
      refusal(
        createOrder({
          body: {
            order_type: "commercial",
            quotation_ids: [draft?.id ?? ""],
            delivery_address: null,
            payment_terms: "full_payment",
            remarks: null,
          },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "quotation_not_accepted" });
  });

  it("changes a draft's header, and refuses once it has moved on", async () => {
    const orderId = seeded("draft");
    const saved = await patchOrder(orderId, {
      body: { delivery_address: "Near the canal", expected_status: "draft" },
      idempotencyKey: key(),
    });
    expect(saved.deliveryAddress).toBe("Near the canal");

    await expect(
      refusal(
        patchOrder(seeded("approved"), {
          body: { remarks: "x", expected_status: "draft" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "status_changed" });
  });

  it("deletes only a never-submitted draft, and only with delete", async () => {
    as("employee");
    const created = await createOrder({
      body: {
        order_type: "commercial",
        quotation_ids: [freeAcceptedQuotation()],
        delivery_address: null,
        payment_terms: "full_payment",
        remarks: null,
      },
      idempotencyKey: key(),
    });
    await expect(refusal(deleteOrder(created.id, key()))).resolves.toEqual({
      status: 403,
      code: "forbidden",
    });

    as("admin");
    const numbered = mockDb.orders.find(
      (item) => item.status === "draft" && item.order_no !== null,
    );
    await expect(refusal(deleteOrder(numbered?.id ?? "", key()))).resolves.toEqual({
      status: 409,
      code: "order_was_submitted",
    });
    await deleteOrder(created.id, key());
    await expect(refusal(getOrder(created.id))).resolves.toMatchObject({ status: 404 });
  });
});

describe("[SO-004] submitOrder and the approval chain", () => {
  afterEach(reset);

  it("numbers the order and walks its chain: managers, Accounts with a remark, then Dispatch", async () => {
    const orderId = seeded("draft");
    const submitted = await submitOrder(orderId, {
      body: { expected_status: "draft" },
      idempotencyKey: key(),
    });
    expect(submitted.status).toBe("submitted");
    expect(submitted.orderNo).toMatch(/^SO\/GJ\/2026-27\/\d{5}$/);
    expect(submitted.lastRejection).not.toBeNull();

    // Each step joins the inbox only when the one before it is approved.
    let accountsWithoutRemark: unknown = null;
    for (const role of submitted.approval?.steps.map((step) => step.role) ?? []) {
      const step = mockDb.approvalSteps.find(
        (item) => item.docId === orderId && item.decision === null && item.closed === null,
      );
      expect(step?.role).toBe(role);
      as(ROLES.find((candidate) => candidate === role) ?? "admin");
      if (role === "account_manager") {
        accountsWithoutRemark = await refusal(
          decideApprovalStep(step?.stepId ?? "", {
            body: { decision: "approve", remark: null },
            idempotencyKey: key(),
          }),
        );
      }
      await decideApprovalStep(step?.stepId ?? "", {
        body: {
          decision: "approve",
          remark: role === "account_manager" ? "Advance received" : null,
        },
        idempotencyKey: key(),
      });
    }

    expect(accountsWithoutRemark).toEqual({ status: 422, code: "remark_required" });
    const approved = await getOrder(orderId);
    expect(approved.status).toBe("approved");
    expect(approved.approval?.steps.every((step) => step.decision === "approve")).toBe(true);
    expect(approved.pdfState).toBe("pending");
  });

  it("returns a rejected order to draft with the reason", async () => {
    as("district_manager");
    const page = await listPendingApprovals({ includeBelow: false, cursor: null });
    const row = page.items.find((item) => item.docType === "sales_order");
    if (row === undefined) {
      throw new Error("No order waits on a District Manager in the mock");
    }
    await decideApprovalStep(row.stepId, {
      body: { decision: "reject", remark: "Confirm the lateral quantity" },
      idempotencyKey: key(),
    });
    const returned = await getOrder(row.document.id);
    expect(returned.status).toBe("draft");
    expect(returned.lastRejection).toMatchObject({
      remark: "Confirm the lateral quantity",
      role: "district_manager",
    });
  });

  it("cancels with a reason, and not once something has shipped", async () => {
    as("admin");
    const cancelled = await cancelOrder(seeded("submitted"), {
      body: { remark: "Farmer bought elsewhere", expected_status: "submitted" },
      idempotencyKey: key(),
    });
    expect(cancelled).toMatchObject({
      status: "cancelled",
      cancelRemark: "Farmer bought elsewhere",
    });

    await expect(
      refusal(
        cancelOrder(seeded("partially_dispatched"), {
          body: { remark: "No", expected_status: "partially_dispatched" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "order_dispatched" });
  });
});

describe("[DISP-002] dispatches", () => {
  afterEach(reset);

  it("records what left, refuses more than is open, voids, and closes the rest short", async () => {
    as("dispatch_manager");
    const orderId = seeded("partially_dispatched");
    const order = await getOrder(orderId);
    const line = order.lines[0];
    if (line === undefined) throw new Error("The order has no lines");
    const base = {
      dc_no: "DC-1",
      dc_date: null,
      invoice_no: null,
      invoice_date: null,
      dispatched_at: new Date(Date.now() - 60_000).toISOString(),
      transporter: null,
      vehicle_no: null,
    };

    await expect(
      refusal(
        createDispatch(orderId, {
          body: {
            ...base,
            lines: [{ order_line_id: line.id, qty: String(Number(line.qtyOpen) + 1) }],
          },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "over_open_quantity" });
    await expect(
      refusal(
        createDispatch(orderId, {
          body: {
            ...base,
            dispatched_at: new Date(Date.now() + 3_600_000).toISOString(),
            lines: [{ order_line_id: line.id, qty: "1" }],
          },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "validation_error" });

    const dispatch = await createDispatch(orderId, {
      body: { ...base, lines: [{ order_line_id: line.id, qty: line.qtyOpen }] },
      idempotencyKey: key(),
    });
    expect(dispatch.lines).toHaveLength(1);
    expect((await getOrder(orderId)).status).toBe("dispatched");

    const reopened = await voidDispatch(dispatch.id, {
      body: { remark: "Wrong truck", expected_status: "dispatched" },
      idempotencyKey: key(),
    });
    expect(reopened.status).toBe("partially_dispatched");
    expect(reopened.dispatches.find((item) => item.id === dispatch.id)?.voidRemark).toBe(
      "Wrong truck",
    );

    const closed = await closeOrderShort(orderId, {
      body: { remark: "Rest not needed", expected_status: "partially_dispatched" },
      idempotencyKey: key(),
    });
    expect(closed.status).toBe("closed_short");
    expect(closed.lines.every((item) => Number(item.qtyOpen) === 0)).toBe(true);
    await expect(
      refusal(
        voidDispatch(dispatch.id, {
          body: { remark: "Again", expected_status: "closed_short" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "dispatch_voided" });
  });

  it("is refused to roles without dispatch", async () => {
    await expect(
      refusal(
        createDispatch(seeded("approved"), {
          body: {
            dc_no: null,
            dc_date: null,
            invoice_no: null,
            invoice_date: null,
            dispatched_at: new Date().toISOString(),
            transporter: null,
            vehicle_no: null,
            lines: [],
          },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 403, code: "forbidden" });
  });
});
