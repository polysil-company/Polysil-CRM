import { afterEach, describe, expect, it } from "vitest";

import { getQuotation, patchQuotation } from "@/features/quotations/api/quotations.api";
import { isApiError } from "@/lib/api/errors";
import { mockDb, resetMockDb } from "@/mocks/db";

import { decideApprovalStep, listPendingApprovals } from "./approvals.api";

let keys = 0;
function key(): string {
  keys += 1;
  return `approvals-test-${String(keys)}`;
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

/** The first waiting quotation step in the previewed role's inbox (State Manager in tests). */
async function firstQuotationRow(): Promise<{ stepId: string; quotationId: string }> {
  const page = await listPendingApprovals({ includeBelow: false, cursor: null });
  const row = page.items.find((item) => item.docType === "quotation");
  if (row === undefined) {
    throw new Error("No quotation waits on a State Manager in the mock");
  }
  return { stepId: row.stepId, quotationId: row.document.id };
}

describe("[APPR-001] listPendingApprovals", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists what waits on the role, oldest first, with the count and both kinds", async () => {
    const page = await listPendingApprovals({ includeBelow: false, cursor: null });

    expect(page.total).toBe(page.items.length);
    expect(page.items.map((row) => row.docType)).toEqual(
      expect.arrayContaining(["quotation", "sales_order"]),
    );
    const times = page.items.map((row) => Date.parse(row.document.raisedAt));
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    // Own steps, and a lower step only when nobody of its role covers it.
    expect(page.items.every((row) => row.role === "state_manager" || row.stalled)).toBe(true);
    expect(page.items.find((row) => row.docType === "quotation")?.document).toMatchObject({
      number: null,
      discountPct: expect.stringMatching(/^\d+\.\d{2}$/),
    });
  });

  it("adds every lower step when asked, to cover a manager on leave", async () => {
    const own = await listPendingApprovals({ includeBelow: false, cursor: null });
    const withBelow = await listPendingApprovals({ includeBelow: true, cursor: null });

    expect(withBelow.items.length).toBeGreaterThan(own.items.length);
    expect(withBelow.items.some((row) => row.role === "district_manager" && !row.stalled)).toBe(
      true,
    );
  });
});

describe("[APPR-001] decideApprovalStep", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("approves a quotation discount: it leaves the inbox and the draft may be sent", async () => {
    const { stepId, quotationId } = await firstQuotationRow();

    await expect(
      decideApprovalStep(stepId, {
        body: { decision: "approve", remark: null },
        idempotencyKey: key(),
      }),
    ).resolves.toEqual({ docType: "quotation", id: quotationId });

    const quotation = await getQuotation(quotationId);
    expect(quotation.discount?.sendGate).toBe("approved");
    expect(quotation.approval?.steps[0]).toMatchObject({ decision: "approve" });
    const page = await listPendingApprovals({ includeBelow: false, cursor: null });
    expect(page.items.some((row) => row.stepId === stepId)).toBe(false);
  });

  it("needs a reason to reject, and returns the draft with it", async () => {
    const { stepId, quotationId } = await firstQuotationRow();

    await expect(
      refusal(
        decideApprovalStep(stepId, {
          body: { decision: "reject", remark: null },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "validation_error" });

    await decideApprovalStep(stepId, {
      body: { decision: "reject", remark: "Offer 8% instead" },
      idempotencyKey: key(),
    });
    const quotation = await getQuotation(quotationId);
    expect(quotation.discount?.sendGate).toBe("returned");
    expect(quotation.approval?.steps[0]?.remark).toBe("Offer 8% instead");
  });

  it("refuses a step already decided, and one whose draft changed after the request", async () => {
    const { stepId } = await firstQuotationRow();
    await decideApprovalStep(stepId, {
      body: { decision: "approve", remark: null },
      idempotencyKey: key(),
    });
    await expect(
      refusal(
        decideApprovalStep(stepId, {
          body: { decision: "approve", remark: null },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "step_already_decided" });

    resetMockDb();
    const next = await firstQuotationRow();
    await patchQuotation(next.quotationId, {
      body: { terms: "Delivery in 10 days", expected_status: "draft" },
      idempotencyKey: key(),
    });
    await expect(
      refusal(
        decideApprovalStep(next.stepId, {
          body: { decision: "approve", remark: null },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "figures_changed" });
  });

  it("decides a sales order and answers with which document it was", async () => {
    const page = await listPendingApprovals({ includeBelow: false, cursor: null });
    const order = page.items.find((row) => row.docType === "sales_order");
    if (order === undefined) {
      throw new Error("No sales order waits on a State Manager in the mock");
    }

    await expect(
      decideApprovalStep(order.stepId, {
        body: { decision: "approve", remark: null },
        idempotencyKey: key(),
      }),
    ).resolves.toEqual({ docType: "sales_order", id: order.document.id });
    expect(mockDb.approvalSteps.find((step) => step.stepId === order.stepId)?.decision).toBe(
      "approve",
    );
  });
});
