import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  DISCOUNT_LIMIT_ROLES,
  ORDER_LIMIT_ROLES,
  THRESHOLD_DOC_TYPES,
  type QueuePageWire,
  type ThresholdDocType,
} from "@/features/approvals/api/approvals.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { stepIsOpen, stepVisibleTo, type MockApprovalStep } from "@/mocks/data/approvals";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { decideComplaintRefundStep } from "./complaints";
import { decideOrderStep, findOrder } from "./orders";
import { findQuotation, recordQuotationEvent, refreshGate } from "./quotations";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * APPR-001 · The backend's approval inbox (backend/docs/api/approvals.md): what waits on the
 * previewed role, oldest first, with lower steps on request and stalled ones always; and the
 * decision, which answers with the quotation or order it decided. Refusals: not_your_step,
 * self_approval, step_already_decided, request_closed, figures_changed, remark_required (to
 * return, and on every Accounts decision).
 *
 * APPR-002 · The approval limits: anyone signed in reads them; `masters.edit` sets one role's
 * limit, company-wide or for a territory, as long as each level stays above the one below
 * (`thresholds_not_increasing`). A new limit decides the next order's chain here too.
 */

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;

function toRow(step: MockApprovalStep): QueuePageWire["data"][number] {
  return {
    step_id: step.stepId,
    seq: step.seq,
    role: step.role,
    stalled: step.stalled,
    doc_type: step.docType,
    document: {
      id: step.docId,
      number: step.number,
      party_name: step.partyName,
      total: step.total,
      is_provisional: step.isProvisional,
      raised_by: step.raisedBy,
      raised_at: step.raisedAt,
      discount_pct: step.discountPct,
      request_remark: step.requestRemark,
    },
    waiting_since: step.raisedAt,
  };
}

const thresholdPutSchema = z.object({
  doc_type: z.enum(THRESHOLD_DOC_TYPES).default("sales_order"),
  role: z.enum(DISCOUNT_LIMIT_ROLES),
  territory_id: z.string().min(1).nullish(),
  max_amount: z.union([z.number(), z.string().regex(/^\d+(\.\d+)?$/)]).nullish(),
});

/** Each role's level in its ladder: a higher level's ceiling stays above a lower one's. */
const LIMIT_LEVELS: Readonly<Record<ThresholdDocType, readonly string[]>> = {
  sales_order: ORDER_LIMIT_ROLES,
  quotation: DISCOUNT_LIMIT_ROLES,
  // A refund climbs the order's three managers (FS-015b).
  complaint: ORDER_LIMIT_ROLES,
};

const decisionSchema = z.object({
  decision: z.enum(["approve", "reject"]),
  remark: z.string().trim().max(1000).nullish(),
});

export const approvalHandlers = [
  http.get(buildApiUrl("/approvals/thresholds"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: mockDb.thresholds });
  }),

  http.put(buildApiUrl("/approvals/thresholds"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required.",
      );
    }
    const raw: unknown = await request.json();
    const serialized = JSON.stringify(raw);
    const replay = mockDb.thresholdWrites.get(key);
    if (replay !== undefined) {
      return replay === serialized
        ? HttpResponse.json({ data: mockDb.thresholds })
        : errorResponse(409, "idempotency_key_reused", "This Idempotency-Key was already used.");
    }
    if (!can(mockPermissionsFor(readMockRole()), "masters", "edit")) {
      return errorResponse(403, "forbidden", "Only an administrator changes approval limits.");
    }
    const parsed = thresholdPutSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        max_amount: "a number, or null for no ceiling",
      });
    }
    const { doc_type: docType, role } = parsed.data;
    const territoryId = parsed.data.territory_id ?? null;
    const territory =
      territoryId === null
        ? null
        : (mockDb.leads.find((lead) => lead.territory.id === territoryId)?.territory ?? null);
    if (territoryId !== null && territory === null) {
      return errorResponse(404, "not_found", "No such territory.");
    }
    const amount = parsed.data.max_amount == null ? null : Number(parsed.data.max_amount);
    const levels = LIMIT_LEVELS[docType];
    if (!levels.includes(role)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        role: `no ${docType} limit for this role`,
      });
    }
    if (docType === "quotation" && amount !== null && amount > 100) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        max_amount: "a discount limit is at most 100",
      });
    }
    if (docType !== "quotation" && amount !== null && amount <= 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        max_amount: "a limit in rupees is above 0",
      });
    }
    if (docType === "quotation" && amount === null && role !== "admin_sales") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        max_amount: "only Admin-Sales may have no limit",
      });
    }
    const group = mockDb.thresholds.filter(
      (row) => row.doc_type === docType && (row.territory?.id ?? null) === territoryId,
    );
    const ceilingOf = (level: string): number | null => {
      if (level === role) {
        return amount;
      }
      const row = group.find((item) => item.role === level);
      return row === undefined || row.max_amount === null ? null : Number(row.max_amount);
    };
    const ceilings = levels.map(ceilingOf).filter((value) => value !== null);
    const increasing = ceilings.every(
      (value, index) => index === 0 || value > (ceilings[index - 1] ?? 0),
    );
    if (!increasing) {
      return errorResponse(
        422,
        "thresholds_not_increasing",
        "A higher manager's limit must be above a lower one's.",
        {
          max_amount: "not above the level below",
        },
      );
    }
    const text = amount === null ? null : amount.toFixed(2);
    const existing = mockDb.thresholds.find(
      (row) =>
        row.doc_type === docType &&
        row.role === role &&
        (row.territory?.id ?? null) === territoryId,
    );
    if (existing !== undefined) {
      existing.max_amount = text;
    } else {
      mockDb.thresholds.push({
        doc_type: docType,
        role,
        territory:
          territory === null
            ? null
            : { id: territory.id, name: territory.name, level: territory.level },
        max_amount: text,
        unit: docType === "quotation" ? "pct" : "inr",
      });
    }
    mockDb.thresholdWrites.set(key, serialized);
    return HttpResponse.json({ data: mockDb.thresholds });
  }),

  http.get(buildApiUrl("/approvals/pending"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }
    const includeBelow = url.searchParams.get("include_below") === "true";
    const role = readMockRole();
    const matches =
      scenario === "empty"
        ? []
        : mockDb.approvalSteps.filter(
            (step) => stepIsOpen(step) && stepVisibleTo(step, role, includeBelow),
          );
    const counted = url.searchParams.get("include_total") === "true";
    const hasMore = offset + limit < matches.length;
    const body: QueuePageWire = {
      data: matches.slice(offset, offset + limit).map(toRow),
      meta: {
        limit,
        next_cursor: hasMore ? encodeCursor(offset + limit) : null,
        total: counted ? Math.min(matches.length, TOTAL_CEILING) : null,
        total_capped: counted && matches.length > TOTAL_CEILING,
      },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/approvals/steps/:stepId/decision"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required.",
      );
    }
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ step: params.stepId, body: raw });
    const replay = mockDb.approvalDecisions.get(key);
    if (replay !== undefined && replay.body !== serialized) {
      return errorResponse(409, "idempotency_key_reused", "This Idempotency-Key was already used.");
    }

    const parsed = decisionSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        decision: "approve or reject",
      });
    }
    const step = mockDb.approvalSteps.find((item) => item.stepId === params.stepId);
    if (step === undefined) {
      return errorResponse(404, "not_found", "No such approval step.");
    }
    const role = readMockRole();
    if (replay === undefined) {
      if (!stepVisibleTo(step, role, true)) {
        return errorResponse(403, "not_your_step", "This step waits on another role.");
      }
      if (step.closed !== null) {
        return step.docType === "quotation" && step.closed === "edited"
          ? errorResponse(409, "figures_changed", "The draft was edited after the request.")
          : errorResponse(409, "request_closed", "The request was withdrawn.");
      }
      if (step.decision !== null) {
        return errorResponse(409, "step_already_decided", "Someone has decided this step.");
      }
      const me = mockMeFor(role).data;
      if (step.raisedBy?.id === me.id) {
        return errorResponse(403, "self_approval", "You cannot decide on your own request.");
      }
      const remark = parsed.data.remark ?? null;
      const remarkNeeded = parsed.data.decision === "reject" || step.role === "account_manager";
      if (remarkNeeded && (remark === null || remark === "")) {
        return errorResponse(422, "remark_required", "Say why.", {
          remark:
            parsed.data.decision === "reject" ? "required to return" : "required from Accounts",
        });
      }
      const decidedAt = new Date().toISOString();
      step.decision = parsed.data.decision;
      step.remark = remark;
      step.decidedAt = decidedAt;
      mockDb.approvalDecisions.set(key, { body: serialized, stepId: step.stepId });

      if (step.docType === "complaint") {
        decideComplaintRefundStep(step.docId, step.stepId, parsed.data.decision, remark, role);
      } else if (step.docType === "quotation") {
        const quotation = findQuotation(step.docId);
        if (quotation?.approval !== null && quotation?.approval !== undefined) {
          quotation.approval = {
            ...quotation.approval,
            status: step.decision === "approve" ? "approved" : "rejected",
            steps: quotation.approval.steps.map((item) =>
              item.id === step.stepId
                ? {
                    ...item,
                    decision: step.decision,
                    decided_role: me.role?.code === item.role ? null : (me.role?.code ?? null),
                    by: { id: me.id, full_name: me.full_name },
                    remark,
                    decided_at: decidedAt,
                  }
                : item,
            ),
          };
          refreshGate(quotation);
          recordQuotationEvent(
            quotation,
            step.decision === "approve"
              ? "quotation.approval_approved"
              : "quotation.approval_returned",
            { role: step.role, remark },
          );
        }
      } else {
        const order = findOrder(step.docId);
        if (order !== undefined) {
          decideOrderStep(order, step.stepId, parsed.data.decision, remark, role);
        }
      }
    }

    if (step.docType === "complaint") {
      const complaint = mockDb.complaints.find((item) => item.id === step.docId);
      return complaint === undefined
        ? errorResponse(404, "not_found", "The complaint is gone.")
        : HttpResponse.json({ data: { ...complaint, doc_type: "complaint" } });
    }
    if (step.docType === "quotation") {
      const quotation = findQuotation(step.docId);
      return quotation === undefined
        ? errorResponse(404, "not_found", "The quotation is gone.")
        : HttpResponse.json({ data: { ...quotation, doc_type: "quotation" } });
    }
    const order = findOrder(step.docId);
    return order === undefined
      ? errorResponse(404, "not_found", "The order is gone.")
      : HttpResponse.json({ data: { ...order, doc_type: "sales_order" } });
  }),
];
