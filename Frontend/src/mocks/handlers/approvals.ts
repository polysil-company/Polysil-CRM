import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { QueuePageWire } from "@/features/approvals/api/approvals.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { stepIsOpen, stepVisibleTo, type MockApprovalStep } from "@/mocks/data/approvals";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

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
    },
    waiting_since: step.raisedAt,
  };
}

const decisionSchema = z.object({
  decision: z.enum(["approve", "reject"]),
  remark: z.string().trim().max(1000).nullish(),
});

export const approvalHandlers = [
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

      if (step.docType === "quotation") {
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
