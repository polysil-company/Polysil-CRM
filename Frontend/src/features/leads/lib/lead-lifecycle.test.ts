import { describe, expect, it } from "vitest";

import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";
import { ApiError } from "@/lib/api/errors";

import { stageActionLabel, stageChangeError, stageMenuFor } from "./lead-lifecycle";

function refusal(status: number, code: string, fields: Record<string, string> = {}): ApiError {
  return new ApiError({
    kind: "http",
    message: code,
    dataId: "LEAD-007",
    requestId: "req-1",
    method: "POST",
    path: "/leads/lead-1/transition",
    status,
    code,
    details: { fields },
  });
}

describe("[LEAD-007] stageMenuFor", () => {
  it("offers the moves the backend's stage machine allows", () => {
    expect(stageMenuFor("new").actions).toEqual([
      { kind: "move", to: "contacted" },
      { kind: "lost" },
    ]);
    expect(stageMenuFor("contacted").actions).toEqual([
      { kind: "move", to: "qualified" },
      { kind: "lost" },
    ]);
    expect(stageMenuFor("qualified").actions).toEqual([{ kind: "lost" }]);
    expect(stageMenuFor("quoted").actions).toEqual([{ kind: "won" }, { kind: "lost" }]);
    expect(stageMenuFor("negotiation").actions).toEqual([{ kind: "won" }, { kind: "lost" }]);
    expect(stageMenuFor("lost").actions).toEqual([{ kind: "reopen" }]);
  });

  it("offers nothing on a closed or dormant lead", () => {
    for (const stage of ["won", "merged", "dormant"] as const) {
      expect(stageMenuFor(stage)).toEqual({ actions: [], hint: null });
    }
  });

  it("says where the quotation-driven steps happen", () => {
    expect(stageMenuFor("qualified").hint).toEqual({
      label: "Quoted",
      reason: "Happens when a quotation is sent",
    });
    expect(stageMenuFor("quoted").hint?.label).toBe("Negotiation");
  });

  it("never offers a move to the stage the lead is already in", () => {
    for (const stage of LEAD_STAGES) {
      const moves = stageMenuFor(stage).actions.flatMap((action) =>
        action.kind === "move" ? [action.to] : [],
      );
      expect(moves, stage).not.toContain(stage);
    }
  });
});

describe("[LEAD-007] stageActionLabel", () => {
  it("names each action", () => {
    expect(stageActionLabel({ kind: "move", to: "contacted" })).toBe("Mark as contacted");
    expect(stageActionLabel({ kind: "won" })).toBe("Mark as won");
    expect(stageActionLabel({ kind: "lost" })).toBe("Mark as lost…");
    expect(stageActionLabel({ kind: "reopen" })).toBe("Reopen lead…");
  });
});

describe("[LEAD-007] stageChangeError", () => {
  it("names the stage a lead moved to while it was open", () => {
    expect(stageChangeError(refusal(409, "stage_changed", { stage: "qualified" }))).toEqual({
      message:
        "Someone moved this lead to Qualified while you had it open. It now shows the latest.",
      stale: true,
    });
    expect(stageChangeError(refusal(409, "stage_changed")).stale).toBe(true);
  });

  it("treats a move the lead no longer allows as out of date", () => {
    expect(stageChangeError(refusal(422, "invalid_transition")).stale).toBe(true);
    expect(stageChangeError(refusal(422, "stage_terminal", { stage: "won" })).stale).toBe(true);
  });

  it("explains that winning needs an accepted quotation", () => {
    expect(stageChangeError(refusal(422, "quotation_required", { to_stage: "won" }))).toEqual({
      message: "A lead is won when a quotation on it is accepted. Accept the quotation first.",
      stale: false,
    });
  });

  it("falls back to the general wording for anything else", () => {
    expect(stageChangeError(refusal(503, "unavailable"))).toEqual({
      message: "Something went wrong on our side",
      stale: false,
    });
    expect(stageChangeError(new Error("offline")).stale).toBe(false);
  });
});
