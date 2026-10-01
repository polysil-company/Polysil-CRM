import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";
import type { Role } from "@/lib/auth/roles";

import { MOCK_ID_SPACE, mockUuid } from "./reference";

/**
 * APPR-001 · The mock's approval queue, for quotation discounts and sales orders. A
 * quotation's request has one step; an order's chain has several, and only the first
 * undecided one is in the queue — the next joins it when that one is approved.
 */
export interface MockApprovalStep {
  readonly stepId: string;
  readonly requestId: string;
  /** The step's place in its chain, from 1. */
  readonly seq: number;
  readonly role: string;
  /** Nobody of the step's own role covers it, so a higher manager may decide it. */
  readonly stalled: boolean;
  readonly docType: "sales_order" | "quotation";
  readonly docId: string;
  readonly number: string | null;
  readonly partyName: string;
  readonly total: string;
  readonly isProvisional: boolean;
  readonly discountPct: string | null;
  readonly raisedBy: { readonly id: string; readonly full_name: string } | null;
  readonly raisedAt: string;
  decision: "approve" | "reject" | null;
  remark: string | null;
  decidedAt: string | null;
  /** The request closed before a decision: its draft was edited or deleted. */
  closed: "edited" | "deleted" | null;
}

/**
 * The lowest manager whose stand-in limit covers a quotation's discount (District 10 %,
 * State 15 %, Regional 20 %). Above that the backend asks Admin-Sales, whom the mock does
 * not seed, so it answers `no_approver`.
 */
const QUOTATION_APPROVER_LIMITS: readonly { readonly upToPct: number; readonly role: string }[] = [
  { upToPct: 10, role: "district_manager" },
  { upToPct: 15, role: "state_manager" },
  { upToPct: 20, role: "regional_manager" },
];

export function quotationApproverFor(effectivePct: number): string | null {
  return QUOTATION_APPROVER_LIMITS.find((limit) => effectivePct <= limit.upToPct)?.role ?? null;
}

/** How high each approving role sits; a step is someone's when the ranks match. */
const STEP_RANK: Readonly<Record<string, number>> = {
  district_manager: 1,
  state_manager: 2,
  regional_manager: 3,
  admin_sales: 4,
};

function rankOfRole(role: Role): number {
  switch (role) {
    case "district_manager":
      return 1;
    case "state_manager":
      return 2;
    case "regional_manager":
      return 3;
    case "admin":
      return 4;
    default:
      return 0;
  }
}

/** Accounts and Dispatch decide only their own steps: no manager covers them. */
const OWN_STEP_ROLES: readonly string[] = ["account_manager", "dispatch_manager"];

/**
 * Whether the signed-in role sees the step in its inbox: its own role's steps; a lower
 * step nobody covers (stalled); and, when asked, every lower step, to cover a manager on
 * leave. Accounts and Dispatch see only their own. Roles that approve nothing see nothing.
 */
export function stepVisibleTo(step: MockApprovalStep, role: Role, includeBelow: boolean): boolean {
  if (OWN_STEP_ROLES.includes(step.role)) {
    return step.role === role;
  }
  const mine = rankOfRole(role);
  const rank = STEP_RANK[step.role] ?? 0;
  if (mine === 0 || rank === 0) {
    return false;
  }
  return rank === mine || (rank < mine && (includeBelow || step.stalled));
}

export function stepIsOpen(step: MockApprovalStep): boolean {
  return step.decision === null && step.closed === null;
}

const HOUR = 60 * 60 * 1000;

/**
 * The queue row for an order's next undecided step, or null when none waits. `stalled`:
 * nobody holds the step's role in the order's office, so a higher manager sees it.
 */
export function orderQueueStep(order: OrderWire, stalled = false): MockApprovalStep | null {
  const approval = order.approval;
  const next = approval?.steps.find((step) => (step.decision ?? null) === null);
  if (approval === null || approval === undefined || next === undefined) {
    return null;
  }
  const previous = approval.steps.filter((step) => step.seq < next.seq).at(-1);
  return {
    stepId: next.id,
    requestId: approval.request_id,
    seq: next.seq,
    role: next.role,
    stalled,
    docType: "sales_order",
    docId: order.id,
    number: order.order_no,
    partyName: order.party.name,
    total: order.totals.total,
    isProvisional: order.is_provisional,
    discountPct: null,
    raisedBy:
      order.owner === null ? null : { id: order.owner.id, full_name: order.owner.full_name },
    raisedAt: previous?.decided_at ?? order.submitted_at ?? order.created_at,
    decision: null,
    remark: null,
    decidedAt: null,
    closed: null,
  };
}

/**
 * Seeds the queue: every other draft whose discount needs approval is waiting on its
 * manager, and every submitted order waits on its next step. Mutates the drafts it puts
 * in the queue.
 */
export function seedApprovals(
  quotations: QuotationWire[],
  orders: readonly OrderWire[],
): MockApprovalStep[] {
  const steps: MockApprovalStep[] = [];
  let index = 0;

  const waiting = quotations.filter(
    (quotation) => quotation.status === "draft" && quotation.discount?.approval_required === true,
  );
  for (const [position, quotation] of waiting.entries()) {
    const effective = Number(quotation.discount?.effective_pct ?? "0");
    const role = quotationApproverFor(effective);
    if (position % 2 === 1 || role === null) {
      continue;
    }
    index += 1;
    const stepId = mockUuid(MOCK_ID_SPACE.approval, index);
    const requestId = mockUuid(MOCK_ID_SPACE.approval, 1000 + index);
    const raisedAt = new Date(Date.parse(quotation.created_at) + 2 * HOUR).toISOString();
    quotation.approval = {
      request_id: requestId,
      status: "pending",
      steps: [
        {
          id: stepId,
          seq: 1,
          role,
          decided_role: null,
          decision: null,
          by: null,
          remark: null,
          decided_at: null,
        },
      ],
      request_remark: "Repeat customer; matching a competitor's offer.",
    };
    if (quotation.discount !== null && quotation.discount !== undefined) {
      quotation.discount = { ...quotation.discount, send_gate: "pending" };
    }
    steps.push({
      stepId,
      requestId,
      seq: 1,
      role,
      stalled: false,
      docType: "quotation",
      docId: quotation.id,
      number: null,
      partyName: quotation.party.name,
      total: quotation.totals.total,
      isProvisional: quotation.is_provisional,
      discountPct: quotation.discount?.effective_pct ?? null,
      raisedBy: quotation.owner,
      raisedAt,
      decision: null,
      remark: null,
      decidedAt: null,
      closed: null,
    });
  }

  // The first order waiting at District stalls, as when a district has no manager.
  let stalledOne = false;
  for (const order of orders.filter((item) => item.status === "submitted")) {
    const waitsOn = order.approval?.steps.find((item) => (item.decision ?? null) === null)?.role;
    const stalled: boolean = !stalledOne && waitsOn === "district_manager";
    stalledOne ||= stalled;
    const step = orderQueueStep(order, stalled);
    if (step !== null) {
      steps.push(step);
    }
  }

  return steps.sort((a, b) => Date.parse(a.raisedAt) - Date.parse(b.raisedAt));
}
