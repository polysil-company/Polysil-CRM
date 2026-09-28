import { afterEach, describe, expect, it } from "vitest";

import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { isApiError } from "@/lib/api/errors";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  createQuotation,
  deleteQuotation,
  getQuotation,
  getQuotationTimeline,
  listQuotationVersions,
  requestQuotationApproval,
  reviseQuotation,
  sendQuotation,
  transitionQuotation,
} from "./quotations.api";
import type { Quotation } from "./quotations.schemas";

let keys = 0;
/** A fresh Idempotency-Key per call. */
function key(): string {
  keys += 1;
  return `test-key-${String(keys)}`;
}

function leadAt(stage: LeadStage): string {
  const lead = mockDb.leads.find((item) => item.stage === stage);
  if (lead === undefined) {
    throw new Error(`No ${stage} lead in the mock database`);
  }
  return lead.id;
}

function stageOf(leadId: string): LeadStage | undefined {
  return mockDb.leads.find((item) => item.id === leadId)?.stage;
}

/** A draft on a qualified lead with one item at `discountPct`; the owner's limit is 5 %. */
async function draftWith(discountPct: string): Promise<Quotation> {
  const product = MOCK_PRODUCTS[0];
  if (product === undefined) {
    throw new Error("No products in the mock catalogue");
  }
  return createQuotation({
    body: {
      lead_id: leadAt("qualified"),
      sales_type: "commercial",
      party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
      terms: null,
      lines: [
        {
          product_id: product.id,
          qty: "10",
          discount_pct: discountPct,
          discount2_pct: "0",
          discount3_pct: "0",
        },
      ],
    },
    idempotencyKey: key(),
  });
}

async function send(quotation: Quotation): Promise<Quotation> {
  return sendQuotation(quotation.id, {
    body: { channel: "whatsapp", expected_status: "draft" },
    idempotencyKey: key(),
  });
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

describe("[QUOT-006] sendQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("numbers the draft, mints the link, renders the PDF, and moves the lead to quoted", async () => {
    const draft = await draftWith("0");
    const leadId = draft.lead?.id ?? "";

    const sent = await send(draft);

    expect(sent).toMatchObject({ status: "sent", pdfState: "pending", discount: null });
    expect(sent.quoteNo).toMatch(/^QT\/GJ\/2026-27\/\d{5}$/);
    expect(sent.shareUrl).toMatch(/\/q\/[\w-]+$/);
    expect(sent.validUntil).not.toBeNull();
    expect(stageOf(leadId)).toBe("quoted");
  });

  it("refuses a discount above the owner's limit until it is approved", async () => {
    const draft = await draftWith("12");
    expect(draft.discount?.sendGate).toBe("required");

    await expect(refusal(send(draft))).resolves.toEqual({
      status: 409,
      code: "discount_approval_required",
    });
  });

  it("refuses a draft with no items", async () => {
    const draft = await createQuotation({
      body: {
        lead_id: leadAt("qualified"),
        sales_type: "commercial",
        party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
        terms: null,
        lines: [],
      },
      idempotencyKey: key(),
    });

    await expect(refusal(send(draft))).resolves.toEqual({ status: 422, code: "no_lines" });
  });
});

describe("[QUOT-007] requestQuotationApproval", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("asks the lowest manager whose limit covers it, then sends once approved", async () => {
    const draft = await draftWith("12");

    const asked = await requestQuotationApproval(draft.id, {
      body: { remark: "Repeat customer" },
      idempotencyKey: key(),
    });
    expect(asked.discount?.sendGate).toBe("pending");
    expect(asked.approval).toMatchObject({
      status: "pending",
      requestRemark: "Repeat customer",
      steps: [{ role: "state_manager", decision: null }],
    });
    await expect(refusal(send(asked))).resolves.toEqual({ status: 409, code: "approval_pending" });

    // The mock's stand-in manager decides on the next read once the time has come.
    mockDb.approvalDecideAt.set(draft.id, 0);
    const approved = await getQuotation(draft.id);
    expect(approved.discount?.sendGate).toBe("approved");
    await expect(send(approved)).resolves.toMatchObject({ status: "sent" });
  });

  it("refuses a discount within the limit, and one no manager may approve", async () => {
    await expect(
      refusal(
        requestQuotationApproval((await draftWith("2")).id, {
          body: { remark: null },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "approval_not_required" });
    await expect(
      refusal(
        requestQuotationApproval((await draftWith("30")).id, {
          body: { remark: null },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "no_approver" });
  });
});

describe("[QUOT-008] transitionQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("records the answer with its remark, and acceptance wins the lead", async () => {
    const sent = await send(await draftWith("0"));
    const leadId = sent.lead?.id ?? "";

    const negotiating = await transitionQuotation(sent.id, {
      body: { to: "negotiation", remark: "Wants 2% more", expected_status: "sent" },
      idempotencyKey: key(),
    });
    expect(negotiating.status).toBe("negotiation");
    expect(stageOf(leadId)).toBe("negotiation");

    const accepted = await transitionQuotation(sent.id, {
      body: { to: "accepted", remark: "Confirmed", expected_status: "negotiation" },
      idempotencyKey: key(),
    });
    expect(accepted).toMatchObject({ status: "accepted", decisionRemark: "Confirmed" });
    expect(accepted.acceptedAt).not.toBeNull();
    expect(stageOf(leadId)).toBe("won");
  });

  it("refuses a stale status, and an answer on an accepted quotation", async () => {
    const sent = await send(await draftWith("0"));

    await expect(
      refusal(
        transitionQuotation(sent.id, {
          body: { to: "rejected", remark: null, expected_status: "viewed" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "status_changed" });

    await transitionQuotation(sent.id, {
      body: { to: "accepted", remark: null, expected_status: "sent" },
      idempotencyKey: key(),
    });
    await expect(
      refusal(
        transitionQuotation(sent.id, {
          body: { to: "rejected", remark: null, expected_status: "accepted" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "invalid_transition" });
  });
});

describe("[QUOT-009] reviseQuotation and versions", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("drafts the next version of the number; sending it supersedes the first", async () => {
    const first = await send(await draftWith("0"));
    await transitionQuotation(first.id, {
      body: { to: "rejected", remark: null, expected_status: "sent" },
      idempotencyKey: key(),
    });

    const second = await reviseQuotation(first.id, {
      body: { price_effective_date: null, expected_status: "rejected" },
      idempotencyKey: key(),
    });
    expect(second).toMatchObject({
      status: "draft",
      version: 2,
      quoteNo: null,
      supersedes: { id: first.id, version: 1 },
    });
    await expect(
      refusal(
        reviseQuotation(first.id, {
          body: { price_effective_date: null, expected_status: "rejected" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "revision_exists" });

    const sentSecond = await send(second);
    expect(sentSecond.quoteNo).toBe(first.quoteNo);
    await expect(getQuotation(first.id)).resolves.toMatchObject({
      supersededBy: { id: second.id, version: 2 },
    });
    const versions = await listQuotationVersions(second.id);
    expect(versions.map((version) => version.version)).toEqual([1, 2]);
  });

  it("refuses to revise a draft", async () => {
    const draft = await draftWith("0");

    await expect(
      refusal(
        reviseQuotation(draft.id, {
          body: { price_effective_date: null, expected_status: "draft" },
          idempotencyKey: key(),
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "invalid_transition" });
  });
});

describe("[QUOT-010] getQuotationTimeline", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists what happened, newest first", async () => {
    const sent = await send(await draftWith("0"));

    const page = await getQuotationTimeline({ quotationId: sent.id, cursor: null });

    expect(page.items.map((event) => event.kind)).toEqual(["quotation.sent", "quotation.created"]);
  });
});

describe("[QUOT-011] deleteQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("deletes a draft, and a retry with the same key is answered the same", async () => {
    const draft = await draftWith("0");
    const input = { body: { expected_status: "draft" as const }, idempotencyKey: key() };

    await expect(deleteQuotation(draft.id, input)).resolves.toBeUndefined();
    await expect(deleteQuotation(draft.id, input)).resolves.toBeUndefined();
    await expect(refusal(getQuotation(draft.id))).resolves.toEqual({
      status: 404,
      code: "not_found",
    });
  });

  it("never deletes a sent quotation", async () => {
    const sent = await send(await draftWith("0"));

    await expect(
      refusal(
        deleteQuotation(sent.id, { body: { expected_status: "draft" }, idempotencyKey: key() }),
      ),
    ).resolves.toEqual({ status: 409, code: "status_changed" });
  });
});
