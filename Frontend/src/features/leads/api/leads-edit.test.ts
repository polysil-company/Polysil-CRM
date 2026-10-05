import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  deleteLead,
  dismissDuplicate,
  getLead,
  getLeadTimeline,
  listDuplicates,
  mergeLead,
  patchLead,
} from "./leads.api";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function leadAt(stage: string): string {
  const lead = mockDb.leads.find((item) => item.stage === stage && item.merged_into === null);
  if (lead === undefined) throw new Error(`No ${stage} lead`);
  return lead.id;
}

describe("[LEAD-010] patchLead", () => {
  afterEach(reset);

  it("changes only what is sent, and records the change on the timeline", async () => {
    writeMockRole("admin");
    const id = leadAt("contacted");
    const before = await getLead(id);
    const lead = await patchLead({
      leadId: id,
      body: { farmer_name: "Kiritbhai Shah", village: null },
      idempotencyKey: "p-1",
    });
    expect(lead).toMatchObject({ customerName: "Kiritbhai Shah", village: null });
    expect(lead.phone).toBe(before.phone);

    const history = await getLeadTimeline({ leadId: id, cursor: null });
    expect(history.items[0]?.kind).toBe("lead.updated");
  });

  it("refuses a closed lead", async () => {
    writeMockRole("admin");
    await expect(
      patchLead({ leadId: leadAt("lost"), body: { village: "Gondal" }, idempotencyKey: "p-2" }),
    ).rejects.toMatchObject({ status: 422, code: "stage_terminal" });
  });
});

describe("[LEAD-011] deleteLead", () => {
  afterEach(reset);

  it("deletes for a holder of leads.delete, and refuses anyone else", async () => {
    const id = leadAt("new");
    writeMockRole("employee");
    await expect(deleteLead({ leadId: id, idempotencyKey: "d-1" })).rejects.toMatchObject({
      status: 403,
    });

    writeMockRole("admin");
    await deleteLead({ leadId: id, idempotencyKey: "d-2" });
    await expect(getLead(id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("[LEAD-012] duplicates", () => {
  afterEach(reset);

  it("lists pending pairs, dismisses one, and merges another into its survivor", async () => {
    writeMockRole("admin");
    const page = await listDuplicates(null);
    expect(page.items.length).toBeGreaterThan(1);
    const open = (stage: string): boolean => !["won", "lost", "merged"].includes(stage);
    const mergeable = page.items.filter((pair) => open(pair.leadA.stage) && open(pair.leadB.stage));
    const second = mergeable[0];
    const first = page.items.find((pair) => pair.linkId !== second?.linkId);
    if (first === undefined || second === undefined) throw new Error("Need two pairs");

    await dismissDuplicate({ linkId: first.linkId, idempotencyKey: "x-1" });
    const after = await listDuplicates(null);
    expect(after.items.map((pair) => pair.linkId)).not.toContain(first.linkId);

    const survivor = await mergeLead({
      leadId: second.leadB.id,
      body: { into_lead_id: second.leadA.id },
      idempotencyKey: "m-1",
    });
    expect(survivor.id).toBe(second.leadA.id);
    const loser = await getLead(second.leadB.id);
    expect(loser).toMatchObject({ stage: "merged", mergedInto: { id: second.leadA.id } });
  });

  it("refuses to merge a lead into itself, or a closed one", async () => {
    writeMockRole("admin");
    const id = leadAt("contacted");
    await expect(
      mergeLead({ leadId: id, body: { into_lead_id: id }, idempotencyKey: "m-2" }),
    ).rejects.toMatchObject({ code: "merge_self" });
    await expect(
      mergeLead({ leadId: id, body: { into_lead_id: leadAt("won") }, idempotencyKey: "m-3" }),
    ).rejects.toMatchObject({ code: "merge_terminal" });
  });
});
