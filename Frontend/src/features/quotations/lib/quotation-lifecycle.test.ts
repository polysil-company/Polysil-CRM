import { describe, expect, it } from "vitest";

import type { TimelineEvent } from "@/features/leads/api/leads.schemas";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { ApiError } from "@/lib/api/errors";

import {
  draftSendNotice,
  lifecycleRefusal,
  quotationActions,
  quotationHistoryEntry,
  sendStepFor,
} from "./quotation-lifecycle";

const TODAY = "2026-09-28";
const EVERYONE = { edit: true, delete: true };

type Shape = Pick<Quotation, "status" | "supersededBy" | "discount" | "validUntil" | "approval">;

function quotation(patch: Partial<Shape> = {}): Shape {
  return {
    status: "sent",
    supersededBy: null,
    discount: null,
    validUntil: "2026-11-12",
    approval: null,
    ...patch,
  };
}

function discount(sendGate: NonNullable<Shape["discount"]>["sendGate"]): Shape["discount"] {
  return { effectivePct: "11.80", ownerLimitPct: "5.00", approvalRequired: true, sendGate };
}

function refusal(status: number, code: string, fields: Record<string, string> = {}): ApiError {
  return new ApiError({
    kind: "http",
    message: code,
    dataId: "QUOT-006",
    requestId: "req-1",
    method: "POST",
    path: "/quotations/q-1/send",
    status,
    code,
    details: { fields },
  });
}

describe("[QUOT-006] sendStepFor", () => {
  it("sends, asks for approval or waits, by the discount's send gate", () => {
    expect(sendStepFor(null)).toEqual({ kind: "send", approved: false });
    expect(sendStepFor("none_needed")).toEqual({ kind: "send", approved: false });
    expect(sendStepFor("approved")).toEqual({ kind: "send", approved: true });
    expect(sendStepFor("pending")).toEqual({ kind: "waiting" });
    expect(sendStepFor("required")).toEqual({ kind: "request-approval", why: "required" });
    expect(sendStepFor("void")).toEqual({ kind: "request-approval", why: "void" });
    expect(sendStepFor("returned")).toEqual({ kind: "request-approval", why: "returned" });
  });
});

describe("[QUOT-008] quotationActions", () => {
  it("offers a draft's edit, send and delete to those who may", () => {
    const draft = quotation({ status: "draft", validUntil: null, discount: discount("required") });

    expect(quotationActions(draft, EVERYONE, TODAY)).toEqual({
      draft: { edit: true, send: { kind: "request-approval", why: "required" }, delete: true },
      answers: [],
      revise: false,
    });
    expect(quotationActions(draft, { edit: true, delete: false }, TODAY).draft?.delete).toBe(false);
    expect(quotationActions(draft, { edit: false, delete: false }, TODAY).draft).toEqual({
      edit: false,
      send: null,
      delete: false,
    });
  });

  it("records an answer on a quotation the customer has, and revises it", () => {
    expect(quotationActions(quotation({ status: "viewed" }), EVERYONE, TODAY)).toEqual({
      draft: null,
      answers: ["accepted", "negotiation", "rejected"],
      revise: true,
    });
    // Negotiation → negotiation is not a move.
    expect(quotationActions(quotation({ status: "negotiation" }), EVERYONE, TODAY).answers).toEqual(
      ["accepted", "rejected"],
    );
  });

  it("only revises one that was rejected or expired, and nothing on an accepted one", () => {
    expect(quotationActions(quotation({ status: "rejected" }), EVERYONE, TODAY)).toMatchObject({
      answers: [],
      revise: true,
    });
    expect(quotationActions(quotation({ status: "expired" }), EVERYONE, TODAY).revise).toBe(true);
    expect(quotationActions(quotation({ status: "accepted" }), EVERYONE, TODAY)).toEqual({
      draft: null,
      answers: [],
      revise: false,
    });
  });

  it("takes no answer past the validity date, even before the nightly job marks it expired", () => {
    const lapsed = quotation({ status: "viewed", validUntil: "2026-09-27" });

    expect(quotationActions(lapsed, EVERYONE, TODAY)).toMatchObject({ answers: [], revise: true });
  });

  it("offers nothing on a superseded version, or to someone who may not edit", () => {
    const superseded = quotation({ status: "rejected", supersededBy: { id: "q-2", version: 2 } });

    expect(quotationActions(superseded, EVERYONE, TODAY)).toEqual({
      draft: null,
      answers: [],
      revise: false,
    });
    expect(
      quotationActions(quotation({ status: "viewed" }), { edit: false, delete: false }, TODAY),
    ).toEqual({ draft: null, answers: [], revise: false });
  });
});

describe("[QUOT-007] draftSendNotice", () => {
  it("says nothing when the discount is within the limit, or once sent", () => {
    expect(draftSendNotice(quotation({ status: "draft", discount: discount("none_needed") }))).toBe(
      null,
    );
    expect(draftSendNotice(quotation({ status: "sent" }))).toBe(null);
  });

  it("explains each approval state, naming the approver's role and remark", () => {
    const step = {
      id: "s-1",
      role: "state_manager",
      decidedRole: null,
      decision: null,
      by: null,
      remark: null,
      decidedAt: null,
    };
    expect(
      draftSendNotice(quotation({ status: "draft", discount: discount("required") })),
    ).toMatchObject({ tone: "warning", detail: expect.stringContaining("11.8%") });
    expect(
      draftSendNotice(
        quotation({
          status: "draft",
          discount: discount("pending"),
          approval: { status: "pending", requestRemark: null, steps: [step] },
        }),
      )?.title,
    ).toBe("Waiting for a State Manager to approve the 11.8% discount");
    expect(
      draftSendNotice(
        quotation({
          status: "draft",
          discount: discount("returned"),
          approval: {
            status: "rejected",
            requestRemark: null,
            steps: [{ ...step, decision: "reject", remark: "Too steep for this district" }],
          },
        }),
      ),
    ).toMatchObject({ tone: "danger", detail: expect.stringContaining("Too steep") });
    expect(draftSendNotice(quotation({ status: "draft", discount: discount("void") }))?.title).toBe(
      "The approval no longer applies",
    );
  });
});

describe("[QUOT-006] lifecycleRefusal", () => {
  it("marks a refusal caused by someone else's change as stale, naming the new status", () => {
    expect(lifecycleRefusal(refusal(409, "status_changed", { status: "accepted" }))).toEqual({
      title: "The quotation has moved on",
      message: "Someone marked it Accepted while you had it open. It now shows the latest.",
      stale: true,
    });
    expect(lifecycleRefusal(refusal(409, "quotation_superseded")).stale).toBe(true);
    expect(lifecycleRefusal(refusal(409, "discount_approval_required")).stale).toBe(true);
  });

  it("keeps refusals the user can act on in the dialog", () => {
    expect(lifecycleRefusal(refusal(409, "rate_changed"))).toMatchObject({
      title: "Prices changed since the draft was saved",
      stale: false,
    });
    expect(lifecycleRefusal(refusal(422, "no_approver")).stale).toBe(false);
    expect(lifecycleRefusal(refusal(422, "no_lines")).stale).toBe(false);
  });
});

describe("[QUOT-010] quotationHistoryEntry", () => {
  function event(kind: string, payload: Record<string, unknown> = {}): TimelineEvent {
    return { id: "e-1", kind, occurredAt: "2026-09-28T10:00:00+05:30", actor: null, payload };
  }

  it("reads each event with its remark, opens, version or approver", () => {
    expect(quotationHistoryEntry(event("quotation.sent", { channel: "none" }))).toEqual({
      title: "Sent",
      detail: "Link shared by hand",
      tone: "info",
    });
    expect(quotationHistoryEntry(event("quotation.viewed", { open_count: 4 })).detail).toBe(
      "4 opens so far",
    );
    expect(
      quotationHistoryEntry(event("quotation.rejected", { remark: "Price too high" })),
    ).toEqual({ title: "Rejected", detail: "Price too high", tone: "danger" });
    expect(quotationHistoryEntry(event("quotation.revised", { version: 3 })).detail).toBe(
      "Into version 3",
    );
    expect(
      quotationHistoryEntry(
        event("quotation.approval_requested", { role: "district_manager", remark: "Bulk order" }),
      ).detail,
    ).toBe("From a District Manager · Bulk order");
  });

  it("keeps an unknown or oddly-shaped event readable", () => {
    expect(quotationHistoryEntry(event("quotation.reminder_sent")).title).toBe("Reminder sent");
    expect(quotationHistoryEntry(event("quotation.viewed", { open_count: "four" })).detail).toBe(
      null,
    );
  });
});
