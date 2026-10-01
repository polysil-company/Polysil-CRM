import { z } from "zod";

import type { TimelineEvent } from "@/features/leads/api/leads.schemas";
import { humanizeCode } from "@/features/lookups/lib/lookup-labels";
import {
  ORDER_STATUSES,
  type OrderLine,
  type OrderStatus,
} from "@/features/orders/api/orders.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";

import { ORDER_STATUS_LABELS, stepRoleLabel } from "./order-labels";

/**
 * SO-003, SO-004, DISP-002 · What can be done with an order, and what the backend's refusals
 * mean (backend/docs/api/orders.md, dispatch.md). The backend enforces every rule — the
 * screen only avoids offering what would be refused.
 */

/** What the signed-in user may do, from `useCan`, and whether the order is theirs. */
export interface OrderPermissions {
  readonly editOrders: boolean;
  readonly deleteOrders: boolean;
  readonly recordDispatch: boolean;
  readonly editDispatch: boolean;
  /** The signed-in user owns the order: an owner cancels their own draft or submitted order. */
  readonly isOwner: boolean;
}

export interface OrderActions {
  /** Change a draft's delivery address, payment terms and remarks. */
  readonly editHeader: boolean;
  readonly submit: boolean;
  /** A draft that was never submitted is deleted; a numbered one is cancelled instead. */
  readonly delete: boolean;
  readonly cancel: boolean;
  readonly recordDispatch: boolean;
  readonly closeShort: boolean;
  readonly voidDispatch: boolean;
}

const SHIPPABLE: readonly OrderStatus[] = ["approved", "partially_dispatched"];
/** A dispatch is voided until the order is closed short or cancelled (409 order_closed). */
const VOIDABLE: readonly OrderStatus[] = [...SHIPPABLE, "dispatched"];

/** What the rules read of an order: its status, whether it was numbered, what has shipped. */
export interface OrderState {
  readonly status: OrderStatus;
  readonly orderNo: string | null;
  readonly lines: readonly Pick<OrderLine, "qtyDispatched">[];
}

function nothingShipped(order: OrderState): boolean {
  return order.lines.every((line) => Number(line.qtyDispatched) === 0);
}

export function orderActions(order: OrderState, can: OrderPermissions): OrderActions {
  const draft = order.status === "draft";
  const shippable = SHIPPABLE.includes(order.status);
  const cancellableByOwner =
    (order.status === "draft" || order.status === "submitted") && (can.isOwner || can.deleteOrders);
  const cancellableApproved =
    order.status === "approved" && nothingShipped(order) && can.deleteOrders;
  return {
    editHeader: draft && can.editOrders,
    submit: draft && can.editOrders,
    delete: draft && order.orderNo === null && can.deleteOrders,
    // A never-submitted draft is deleted rather than cancelled, when the user may delete.
    cancel:
      !(draft && order.orderNo === null && can.deleteOrders) &&
      (cancellableByOwner || cancellableApproved),
    recordDispatch: shippable && can.recordDispatch,
    closeShort: shippable && can.editDispatch,
    voidDispatch: VOIDABLE.includes(order.status) && can.editDispatch,
  };
}

/** A refusal in words, and whether the order on screen is out of date. */
export interface OrderRefusal {
  readonly title: string;
  readonly message: string;
  /** The page should show the latest: someone else moved the order. */
  readonly stale: boolean;
}

const refusalSchema = z.object({
  fields: z.record(z.string(), z.string()).optional(),
});

/** Why the backend refused a save, a submit, a cancel, a dispatch, a void or a close. */
export function orderRefusal(error: unknown): OrderRefusal {
  if (!isApiError(error)) {
    const view = toUserFacingError(error);
    return { title: view.title, message: view.description, stale: false };
  }
  const fields = refusalSchema.safeParse(error.details).data?.fields ?? {};
  const status = z.enum(ORDER_STATUSES).safeParse(fields.status).data;

  switch (error.code) {
    case "status_changed":
      return {
        title: "The order has moved on",
        message:
          status === undefined
            ? "Someone changed it while you had it open. It now shows the latest."
            : `It is now ${ORDER_STATUS_LABELS[status]}: someone changed it while you had it open. It now shows the latest.`,
        stale: true,
      };
    case "order_not_draft":
      return {
        title: "It was submitted already",
        message: "Only a draft can change. The order now shows the latest.",
        stale: true,
      };
    case "order_was_submitted":
      return {
        title: "A submitted order is cancelled, not deleted",
        message: "It has a number, so it stays on record. Cancel it with a reason instead.",
        stale: true,
      };
    case "order_dispatched":
      return {
        title: "Something has shipped",
        message: "An order with a dispatch can't be cancelled. Close it short instead.",
        stale: true,
      };
    case "order_not_cancellable":
      return { title: "This order can't be cancelled now", message: error.message, stale: true };
    case "order_not_dispatchable":
      return {
        title: "The order isn't open for dispatch",
        message: "Only an approved or partly dispatched order ships. It now shows the latest.",
        stale: true,
      };
    case "order_closed":
      return {
        title: "The order is closed",
        message: "Its dispatches can no longer change.",
        stale: true,
      };
    case "dispatch_voided":
      return {
        title: "Already void",
        message: "Someone voided this dispatch already.",
        stale: true,
      };
    case "no_lines":
      return {
        title: "The order has no items",
        message: "An order needs at least one line.",
        stale: false,
      };
    case "zero_total":
      return {
        title: "The order's total is zero",
        message: "Check the lines' quantities and rates.",
        stale: false,
      };
    case "no_approver":
      return {
        title: "Nobody can approve this order",
        message: "No one holds a role the approval chain needs. Ask an administrator to fill it.",
        stale: false,
      };
    case "rate_changed":
      return {
        title: "Prices changed since the draft was saved",
        message:
          "A price list or tax rate was published meanwhile. The order shows the new figures — check them and submit again.",
        stale: true,
      };
    case "lead_not_open":
      return {
        title: "The lead is closed",
        message: `${error.message} Reopen the lead from its page first.`,
        stale: false,
      };
    case "seller_registration_ended":
      return {
        title: "The selling registration has ended",
        message: "Ask an administrator to set the current GST registration, then submit.",
        stale: false,
      };
    case "quotation_on_order":
      return {
        title: "The quotation is already on an order",
        message: "Each accepted quotation goes on one live order. Open that order instead.",
        stale: true,
      };
    case "quotation_not_accepted":
      return {
        title: "Only an accepted quotation is ordered",
        message: error.message,
        stale: true,
      };
    case "quotations_disagree":
      return {
        title: "The quotations don't match",
        message:
          "Quotations on one order must share the partner, place of supply, seller, price date, office and territory.",
        stale: false,
      };
    case "partner_required":
      return {
        title: "A dealer is needed",
        message: "Quotations from several leads make one order only through their dealer.",
        stale: false,
      };
    case "order_type_unsupported":
      return { title: "This order type isn't available yet", message: error.message, stale: false };
    default: {
      const view = toUserFacingError(error);
      return { title: view.title, message: view.description, stale: false };
    }
  }
}

/** One line of the order's history. */
export interface OrderHistoryEntry {
  readonly title: string;
  readonly detail: string | null;
  readonly tone: "neutral" | "info" | "success" | "warning" | "danger";
}

const text = z.string().trim().min(1).nullish().catch(null);

/** Turns one event into the line the history shows. Unknown kinds keep a readable label. */
export function orderHistoryEntry(event: TimelineEvent): OrderHistoryEntry {
  const { payload } = event;
  const remark = text.parse(payload.remark) ?? null;
  const role = text.parse(payload.role) ?? null;
  const dispatchNo = text.parse(payload.dispatch_no) ?? null;
  switch (event.kind) {
    case "order.created":
      return { title: "Drafted", detail: null, tone: "neutral" };
    case "order.updated":
      return { title: "Delivery or terms edited", detail: null, tone: "neutral" };
    case "order.lines_replaced":
      return { title: "Items changed", detail: null, tone: "neutral" };
    case "order.submitted":
      return {
        title: "Submitted for approval",
        detail: text.parse(payload.order_no) ?? null,
        tone: "info",
      };
    case "approval.decided": {
      const approved = payload.decision === "approve";
      const who = role === null ? null : stepRoleLabel(role);
      return {
        title: approved
          ? `Approved${who === null ? "" : ` by ${who}`}`
          : `Returned${who === null ? "" : ` by ${who}`}`,
        detail: remark,
        tone: approved ? "success" : "danger",
      };
    }
    case "order.returned":
      return { title: "Returned to draft", detail: remark, tone: "danger" };
    case "order.approved":
      return {
        title: "Order approved",
        detail: "The PDF is made and the customer is told",
        tone: "success",
      };
    case "order.confirmed":
      return { title: "Customer told", detail: null, tone: "info" };
    case "dispatch.recorded":
      return { title: "Dispatch recorded", detail: dispatchNo, tone: "info" };
    case "dispatch.voided":
      return {
        title: "Dispatch voided",
        detail: [dispatchNo, remark].filter((part) => part !== null).join(" · ") || null,
        tone: "warning",
      };
    case "order.closed_short":
      return { title: "Closed short", detail: remark, tone: "warning" };
    case "order.cancelled":
      return { title: "Cancelled", detail: remark, tone: "danger" };
    case "order.deleted":
      return { title: "Deleted", detail: null, tone: "danger" };
    default:
      return {
        title: humanizeCode(
          event.kind.replace(/^(order|dispatch|approval)\./, "").replace(/\./g, " "),
        ),
        detail: remark,
        tone: "neutral",
      };
  }
}
