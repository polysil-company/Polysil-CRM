import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";
import type { Role } from "@/lib/auth/roles";

import { MOCK_ID_SPACE, mockUuid } from "./reference";

/**
 * APPR-001 · The mock's approval queue: one step per request, for quotation discounts and
 * for sales orders. Orders have no module on the frontend yet, so their rows are seeded here
 * with just what the queue shows.
 */
export interface MockApprovalStep {
  readonly stepId: string;
  readonly requestId: string;
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

/**
 * Whether the signed-in role sees the step in its inbox: its own role's steps; a lower
 * step nobody covers (stalled); and, when asked, every lower step, to cover a manager on
 * leave. Roles that approve nothing see nothing.
 */
export function stepVisibleTo(step: MockApprovalStep, role: Role, includeBelow: boolean): boolean {
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
 * Seeds the queue: every other draft whose discount needs approval is waiting on its
 * manager, and four sales orders wait at District, State and Regional level — one stalled,
 * as when a district has no manager. Mutates the drafts it puts in the queue.
 */
export function seedApprovals(
  quotations: QuotationWire[],
  leads: readonly LeadWire[],
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

  const orderLeads = leads.filter((lead) => lead.stage === "won").slice(0, 4);
  const orderSeeds = [
    { role: "state_manager", stalled: false, total: "845600.00", hoursAgo: 5 },
    { role: "state_manager", stalled: false, total: "1267350.50", hoursAgo: 27 },
    { role: "district_manager", stalled: true, total: "312480.00", hoursAgo: 50 },
    { role: "regional_manager", stalled: false, total: "2485000.00", hoursAgo: 3 },
  ] as const;
  for (const [position, seed] of orderSeeds.entries()) {
    const lead = orderLeads[position];
    if (lead === undefined) {
      break;
    }
    index += 1;
    const serial = String(41 + position).padStart(5, "0");
    steps.push({
      stepId: mockUuid(MOCK_ID_SPACE.approval, index),
      requestId: mockUuid(MOCK_ID_SPACE.approval, 1000 + index),
      role: seed.role,
      stalled: seed.stalled,
      docType: "sales_order",
      docId: mockUuid(MOCK_ID_SPACE.approval, 2000 + index),
      number: `SO/GJ/2026-27/${serial}`,
      partyName: lead.farmer_name,
      total: seed.total,
      isProvisional: false,
      discountPct: null,
      raisedBy: lead.owner,
      raisedAt: new Date(Date.now() - seed.hoursAgo * HOUR).toISOString(),
      decision: null,
      remark: null,
      decidedAt: null,
      closed: null,
    });
  }

  return steps.sort((a, b) => Date.parse(a.raisedAt) - Date.parse(b.raisedAt));
}
