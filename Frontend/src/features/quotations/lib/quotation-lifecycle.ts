import { z } from "zod";

import type { TimelineEvent } from "@/features/leads/api/leads.schemas";
import { humanizeCode } from "@/features/lookups/lib/lookup-labels";
import type {
  Quotation,
  QuotationAnswer,
  QuotationStatus,
  SendGate,
} from "@/features/quotations/api/quotations.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { ROLE_LABELS, ROLES } from "@/lib/auth/roles";

import { QUOTATION_STATUS_LABELS, formatRate } from "./quotation-labels";

/**
 * QUOT-006 … QUOT-011 · What can be done with a quotation, and what the backend's refusals
 * mean. The rules are the contract's (backend/docs/handover/quotations-api-contract.md §2 and
 * §4); the backend enforces them — the screen only avoids offering what would be refused.
 */

/** The statuses whose customer answer can still be recorded. */
const ANSWERABLE: readonly QuotationStatus[] = ["sent", "viewed", "negotiation"];
/** A revision is a new offer: from a quotation the customer has, never a draft or an accepted one. */
const REVISABLE: readonly QuotationStatus[] = [
  "sent",
  "viewed",
  "negotiation",
  "rejected",
  "expired",
];

/** What the signed-in user may do, from `useCan`. */
export interface QuotationPermissions {
  readonly edit: boolean;
  readonly delete: boolean;
}

/** How a draft may be sent, by its discount's `send_gate`. */
export type SendStep =
  | { readonly kind: "send"; readonly approved: boolean }
  | { readonly kind: "request-approval"; readonly why: "required" | "void" | "returned" }
  | { readonly kind: "waiting" };

export interface QuotationActions {
  /** A draft: edit, then send or ask for approval. Null on a sent quotation. */
  readonly draft: {
    readonly edit: boolean;
    readonly send: SendStep | null;
    readonly delete: boolean;
  } | null;
  /** The answers that can be recorded now, in the order the menu offers them. */
  readonly answers: readonly QuotationAnswer[];
  readonly revise: boolean;
}

export function sendStepFor(gate: SendGate | null): SendStep {
  switch (gate) {
    case null:
    case "none_needed":
      return { kind: "send", approved: false };
    case "approved":
      return { kind: "send", approved: true };
    case "pending":
      return { kind: "waiting" };
    case "required":
    case "void":
    case "returned":
      return { kind: "request-approval", why: gate };
  }
}

/** The actions the quotation offers to this user. A superseded version offers none. */
export function quotationActions(
  quotation: Pick<Quotation, "status" | "supersededBy" | "discount" | "validUntil">,
  can: QuotationPermissions,
  today: string,
): QuotationActions {
  if (quotation.supersededBy !== null) {
    return { draft: null, answers: [], revise: false };
  }
  if (quotation.status === "draft") {
    return {
      draft: {
        edit: can.edit,
        send: can.edit ? sendStepFor(quotation.discount?.sendGate ?? null) : null,
        delete: can.delete,
      },
      answers: [],
      revise: false,
    };
  }
  const expired = quotation.validUntil !== null && quotation.validUntil < today;
  const answers: QuotationAnswer[] =
    can.edit && ANSWERABLE.includes(quotation.status) && !expired
      ? [
          "accepted",
          ...(quotation.status === "negotiation" ? [] : ["negotiation" as const]),
          "rejected",
        ]
      : [];
  return {
    draft: null,
    answers,
    revise: can.edit && REVISABLE.includes(quotation.status),
  };
}

export const ANSWER_LABELS: Readonly<Record<QuotationAnswer, string>> = {
  accepted: "Accepted",
  negotiation: "In negotiation",
  rejected: "Rejected",
};

/** "State Manager" for a role code; an unknown code is humanised. */
export function roleLabel(code: string): string {
  const role = ROLES.find((candidate) => candidate === code);
  return role === undefined ? humanizeCode(code) : ROLE_LABELS[role];
}

const refusalSchema = z.object({
  fields: z.record(z.string(), z.string()).optional(),
});

/** A refusal in words, and whether the quotation on screen is out of date. */
export interface LifecycleRefusal {
  readonly title: string;
  readonly message: string;
  /** The page should show the latest: someone else moved the quotation. */
  readonly stale: boolean;
}

/** Why the backend refused a send, an approval request, an answer, a revision or a delete. */
export function lifecycleRefusal(error: unknown): LifecycleRefusal {
  if (!isApiError(error)) {
    const view = toUserFacingError(error);
    return { title: view.title, message: view.description, stale: false };
  }
  const fields = refusalSchema.safeParse(error.details).data?.fields ?? {};
  const status = z
    .enum(["draft", "sent", "viewed", "negotiation", "accepted", "rejected", "expired"])
    .safeParse(fields.status).data;

  switch (error.code) {
    case "status_changed":
      return {
        title: "The quotation has moved on",
        message:
          status === undefined
            ? "Someone changed it while you had it open. It now shows the latest."
            : `Someone marked it ${QUOTATION_STATUS_LABELS[status]} while you had it open. It now shows the latest.`,
        stale: true,
      };
    case "quotation_not_draft":
      return {
        title: "It was sent already",
        message: "Someone sent this quotation while you had it open. It now shows the latest.",
        stale: true,
      };
    case "quotation_superseded":
      return {
        title: "A newer version replaced this one",
        message: "Open the latest version to record the answer or revise it.",
        stale: true,
      };
    case "discount_approval_required":
      return {
        title: "The discount needs approval",
        message: "It is above your limit. Ask a manager to approve it, then send.",
        stale: true,
      };
    case "approval_pending":
      return {
        title: "Waiting for approval",
        message: "A manager has the discount to approve. Send once they have.",
        stale: true,
      };
    case "approval_not_required":
      return {
        title: "No approval needed",
        message: "The discount is within your limit — send the quotation.",
        stale: true,
      };
    case "no_approver":
      return {
        title: "No manager can approve this discount",
        message: "It is above every manager's limit. Lower the discount, or ask an administrator.",
        stale: false,
      };
    case "no_lines":
      return {
        title: "The quotation has no items",
        message: "Edit the draft and add at least one item, then send.",
        stale: false,
      };
    case "rate_changed":
      return {
        title: "Prices changed since the draft was saved",
        message:
          "A price list or tax rate was published meanwhile. Open the draft, check the new figures and save it, then send.",
        stale: false,
      };
    case "predecessor_accepted":
      return {
        title: "The earlier version was accepted",
        message: "The customer accepted the version this one revises, so this draft can't be sent.",
        stale: true,
      };
    case "lead_not_open":
      return {
        title: "The lead is closed",
        message: `${error.message} Reopen the lead from its page first.`,
        stale: false,
      };
    case "quotation_expired":
      return {
        title: "The quotation has expired",
        message: "It is past its validity. Revise it into a new version at today's prices.",
        stale: true,
      };
    case "invalid_transition":
      return { title: "That can't be done now", message: error.message, stale: true };
    case "revision_exists":
      return {
        title: "A revision is already being drafted",
        message: `${error.message} Open it from Versions.`,
        stale: true,
      };
    default: {
      const view = toUserFacingError(error);
      return { title: view.title, message: view.description, stale: false };
    }
  }
}

/** One line of the quotation's history. */
export interface QuotationHistoryEntry {
  readonly title: string;
  readonly detail: string | null;
  readonly tone: "neutral" | "info" | "success" | "warning" | "danger";
}

const text = z.string().trim().min(1).nullish().catch(null);
const count = z.number().int().nonnegative().nullish().catch(null);

/** Turns one event into the line the history shows. Unknown kinds keep a readable label. */
export function quotationHistoryEntry(event: TimelineEvent): QuotationHistoryEntry {
  const { payload } = event;
  const remark = text.parse(payload.remark) ?? null;
  const role = text.parse(payload.role);
  switch (event.kind) {
    case "quotation.created":
      return { title: "Drafted", detail: null, tone: "neutral" };
    case "quotation.updated":
      return { title: "Customer or terms edited", detail: null, tone: "neutral" };
    case "quotation.lines_replaced":
      return { title: "Items changed", detail: null, tone: "neutral" };
    case "quotation.sent":
      return {
        title: "Sent",
        detail: payload.channel === "none" ? "Link shared by hand" : "Sent on WhatsApp",
        tone: "info",
      };
    case "quotation.viewed": {
      const opens = count.parse(payload.open_count) ?? null;
      return {
        title: "Opened by the customer",
        detail: opens === null || opens <= 1 ? null : `${String(opens)} opens so far`,
        tone: "info",
      };
    }
    case "quotation.accepted":
      return { title: "Accepted", detail: remark, tone: "success" };
    case "quotation.rejected":
      return { title: "Rejected", detail: remark, tone: "danger" };
    case "quotation.negotiation":
      return { title: "In negotiation", detail: remark, tone: "warning" };
    case "quotation.expired":
      return { title: "Expired", detail: "Past its validity", tone: "neutral" };
    case "quotation.revised": {
      const version = count.parse(payload.version) ?? null;
      return {
        title: "Revised",
        detail: version === null ? null : `Into version ${String(version)}`,
        tone: "info",
      };
    }
    case "quotation.deleted":
      return { title: "Deleted", detail: null, tone: "danger" };
    case "quotation.approval_requested":
      return {
        title: "Discount approval asked",
        detail:
          [role === null || role === undefined ? null : `From a ${roleLabel(role)}`, remark]
            .filter((part) => part !== null)
            .join(" · ") || null,
        tone: "warning",
      };
    case "quotation.approval_approved":
      return { title: "Discount approved", detail: remark, tone: "success" };
    case "quotation.approval_returned":
      return { title: "Discount approval refused", detail: remark, tone: "danger" };
    case "quotation.approval_cancelled":
      return {
        title: "Discount approval cancelled",
        detail: "The figures changed after it was asked",
        tone: "neutral",
      };
    default:
      return {
        title: humanizeCode(event.kind.replace(/^quotation\./, "").replace(/\./g, " ")),
        detail: remark,
        tone: "neutral",
      };
  }
}

/** What the draft's discount means for sending, as a notice; null when there is nothing to say. */
export interface DraftSendNotice {
  readonly tone: "info" | "warning" | "danger" | "success";
  readonly title: string;
  readonly detail: string | null;
}

export function draftSendNotice(
  quotation: Pick<Quotation, "status" | "discount" | "approval">,
): DraftSendNotice | null {
  const { discount, approval } = quotation;
  if (quotation.status !== "draft" || discount === null) {
    return null;
  }
  const effective = formatRate(discount.effectivePct);
  const limit = discount.ownerLimitPct === null ? null : formatRate(discount.ownerLimitPct);
  const step = approval?.steps[0] ?? null;
  const approver = step === null ? "a manager" : `a ${roleLabel(step.decidedRole ?? step.role)}`;

  switch (discount.sendGate) {
    case "none_needed":
      return null;
    case "required":
      return {
        tone: "warning",
        title: "The discount needs a manager's approval",
        detail: `${effective} off the list price is above your limit${limit === null ? "" : ` of ${limit}`}. Ask for approval, then send.`,
      };
    case "pending":
      return {
        tone: "info",
        title: `Waiting for ${approver} to approve the ${effective} discount`,
        detail:
          "Editing or deleting the draft withdraws the request, so the approval is always for the figures on screen.",
      };
    case "approved":
      return {
        tone: "success",
        title: "Discount approved",
        detail: [
          step?.by === null || step?.by === undefined
            ? null
            : `By ${step.by.name}${step.remark === null ? "" : `: “${step.remark}”`}`,
          "Send when ready.",
        ]
          .filter((part) => part !== null)
          .join(" · "),
      };
    case "void":
      return {
        tone: "warning",
        title: "The approval no longer applies",
        detail: "The figures changed after it was given. Ask for approval again.",
      };
    case "returned":
      return {
        tone: "danger",
        title: "The discount approval was refused",
        detail: [
          step?.remark === null || step?.remark === undefined ? null : `“${step.remark}”`,
          "Change the discount, then ask again.",
        ]
          .filter((part) => part !== null)
          .join(" "),
      };
  }
}
