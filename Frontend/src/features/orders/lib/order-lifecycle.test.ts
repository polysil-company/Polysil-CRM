import { describe, expect, it } from "vitest";

import type { TimelineEvent } from "@/features/leads/api/leads.schemas";
import type { OrderLine } from "@/features/orders/api/orders.schemas";
import { ApiError } from "@/lib/api/errors";

import { formatOrderQty, stepRoleLabel, waitingOnLabel } from "./order-labels";
import {
  orderActions,
  orderHistoryEntry,
  orderRefusal,
  type OrderPermissions,
} from "./order-lifecycle";

const NONE: OrderPermissions = {
  editOrders: false,
  deleteOrders: false,
  recordDispatch: false,
  editDispatch: false,
  isOwner: false,
  isStaff: true,
};
const FIELD: OrderPermissions = { ...NONE, editOrders: true, isOwner: true };
const DISPATCH: OrderPermissions = { ...NONE, recordDispatch: true, editDispatch: true };
const ADMIN: OrderPermissions = {
  editOrders: true,
  deleteOrders: true,
  recordDispatch: true,
  editDispatch: true,
  isOwner: false,
  isStaff: true,
};

function refused(status: number, code: string, fields: Record<string, string> = {}): ApiError {
  return new ApiError({
    kind: "http",
    message: code,
    dataId: "SO-004",
    requestId: "req-1",
    method: "POST",
    path: "/orders/o-1/submit",
    status,
    code,
    details: { fields },
  });
}

function lines(sent: string): Pick<OrderLine, "qtyDispatched">[] {
  return [{ qtyDispatched: sent }];
}

describe("[SO-004] orderActions", () => {
  it("lets the owner edit, submit and cancel a draft; only a holder of delete deletes one", () => {
    const draft = { status: "draft" as const, orderNo: null, lines: lines("0.000") };
    expect(orderActions(draft, FIELD)).toMatchObject({
      editHeader: true,
      submit: true,
      delete: false,
      cancel: true,
      recordDispatch: false,
    });
    expect(orderActions(draft, ADMIN)).toMatchObject({ delete: true, cancel: false });
    // A numbered draft (returned) is cancelled, never deleted.
    expect(orderActions({ ...draft, orderNo: "SO/GJ/2026-27/00001" }, ADMIN)).toMatchObject({
      delete: false,
      cancel: true,
    });
  });

  it("offers nothing to change while it waits, but the owner may cancel", () => {
    const submitted = { status: "submitted" as const, orderNo: "SO/1", lines: lines("0.000") };
    expect(orderActions(submitted, FIELD)).toMatchObject({
      editHeader: false,
      submit: false,
      cancel: true,
    });
    expect(orderActions(submitted, { ...FIELD, isOwner: false })).toMatchObject({ cancel: false });
  });

  it("gives Dispatch the dispatch actions on an approved order, and void on a dispatched one", () => {
    const approved = { status: "approved" as const, orderNo: "SO/1", lines: lines("0.000") };
    expect(orderActions(approved, DISPATCH)).toMatchObject({
      recordDispatch: true,
      closeShort: true,
      voidDispatch: true,
      cancel: false,
    });
    expect(orderActions(approved, FIELD)).toMatchObject({ recordDispatch: false, cancel: false });
    // An approved order with nothing shipped is cancelled by a holder of delete only.
    expect(orderActions(approved, ADMIN).cancel).toBe(true);
    expect(orderActions({ ...approved, lines: lines("2.000") }, ADMIN).cancel).toBe(false);

    const dispatched = { status: "dispatched" as const, orderNo: "SO/1", lines: lines("5.000") };
    expect(orderActions(dispatched, DISPATCH)).toMatchObject({
      recordDispatch: false,
      closeShort: false,
      voidDispatch: true,
    });
    const closed = { status: "closed_short" as const, orderNo: "SO/1", lines: lines("5.000") };
    expect(orderActions(closed, ADMIN)).toEqual({
      editHeader: false,
      submit: false,
      delete: false,
      cancel: false,
      recordDispatch: false,
      closeShort: false,
      voidDispatch: false,
      amend: false,
    });
  });
});

describe("[SO-004] orderRefusal", () => {
  it("says what happened, and marks refusals that mean the page is out of date", () => {
    const moved = orderRefusal(refused(409, "status_changed", { status: "approved" }));
    expect(moved).toMatchObject({ stale: true });
    expect(moved.message).toContain("Approved");
    expect(orderRefusal(refused(422, "no_approver"))).toMatchObject({
      title: "Nobody can approve this order",
      stale: false,
    });
    expect(orderRefusal(refused(409, "order_dispatched")).stale).toBe(true);
  });
});

describe("[SO-002] orderHistoryEntry", () => {
  const event = (kind: string, payload: Record<string, unknown>): TimelineEvent => ({
    id: kind,
    kind,
    occurredAt: "2026-09-28T10:00:00.000Z",
    actor: null,
    payload,
  });

  it("names each step's decision by its desk, with the reason", () => {
    expect(
      orderHistoryEntry(
        event("approval.decided", { role: "account_manager", decision: "approve", remark: "Paid" }),
      ),
    ).toEqual({
      title: "Approved by Accounts",
      detail: "Paid",
      tone: "success",
    });
    expect(
      orderHistoryEntry(
        event("approval.decided", {
          role: "district_manager",
          decision: "reject",
          remark: "Fix it",
        }),
      ),
    ).toMatchObject({
      title: "Returned by District Manager",
      tone: "danger",
    });
    expect(
      orderHistoryEntry(event("dispatch.voided", { dispatch_no: "D/1", remark: "Wrong truck" }))
        .detail,
    ).toBe("D/1 · Wrong truck");
    expect(orderHistoryEntry(event("order.something_new", {})).title).toBe("Something new");
  });
});

describe("[SO-001] order labels", () => {
  it("shows quantities in the unit's precision and names Accounts and Dispatch by their desks", () => {
    expect(formatOrderQty("12.000", 0)).toBe("12");
    expect(formatOrderQty("2.500", 3)).toBe("2.5");
    expect(stepRoleLabel("dispatch_manager")).toBe("Dispatch");
    expect(waitingOnLabel("state_manager")).toBe("Waiting on State Manager");
    expect(waitingOnLabel(null)).toBeNull();
  });
});

describe("[SO-007] Amend an approved order", () => {
  const approved = {
    status: "approved" as const,
    orderNo: "SO/GJ/2026-27/00001",
    lines: lines("0.000"),
    orderType: "commercial" as const,
  };

  it("is offered to staff who edit orders or own it, while nothing has shipped", () => {
    expect(orderActions(approved, FIELD).amend).toBe(true);
    expect(orderActions(approved, ADMIN).amend).toBe(true);
    expect(orderActions(approved, { ...NONE, isOwner: true }).amend).toBe(true);
    expect(orderActions(approved, DISPATCH).amend).toBe(false);
  });

  it("isn't offered to a partner, after a dispatch, on a replacement, or before approval", () => {
    expect(orderActions(approved, { ...FIELD, isStaff: false }).amend).toBe(false);
    expect(orderActions({ ...approved, lines: lines("1.000") }, ADMIN).amend).toBe(false);
    expect(orderActions({ ...approved, orderType: "replacement" }, ADMIN).amend).toBe(false);
    expect(orderActions({ ...approved, status: "submitted" }, ADMIN).amend).toBe(false);
    expect(orderActions({ ...approved, status: "partially_dispatched" }, ADMIN).amend).toBe(false);
  });

  it("says why the backend refused, in the user's words", () => {
    expect(orderRefusal(refused(409, "voided_dispatch_holds_lines"))).toMatchObject({
      title: "This order had a dispatch voided",
      message: "Its items can't change now. Cancel it and create a new one.",
      stale: false,
    });
    expect(orderRefusal(refused(409, "order_has_payments")).title).toBe(
      "Money is allocated to this order",
    );
    expect(orderRefusal(refused(422, "order_type_fixed")).title).toBe(
      "A replacement order can't be amended",
    );
    expect(orderRefusal(refused(409, "order_dispatched")).stale).toBe(true);
  });

  it("writes the amend in the order's history with the total it was approved at", () => {
    const event = (kind: string, payload: Record<string, unknown>): TimelineEvent => ({
      id: kind,
      kind,
      occurredAt: "2026-10-13T10:00:00.000Z",
      actor: null,
      payload,
    });
    expect(
      orderHistoryEntry(
        event("order.amended", { from: "approved", to: "draft", from_total: "105000.00" }),
      ),
    ).toEqual({
      title: "Amended: back to draft",
      detail: "It was approved at ₹1,05,000.00",
      tone: "warning",
    });
  });
});
