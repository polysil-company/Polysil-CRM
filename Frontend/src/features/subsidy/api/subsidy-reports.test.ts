import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { resetMockDb } from "@/mocks/db";

import { listApplications, recordStage } from "./subsidy-applications.api";
import { getAgeing, getStageReport, getSupplyReport } from "./subsidy-reports.api";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

const NONE = { status: null, stage: null, q: "" } as const;

describe("[SUBS-009] Subsidy ageing", () => {
  afterEach(reset);

  it("gives six figures per application: null before a start, running with no end", async () => {
    const page = await getAgeing({ ...NONE, cursor: null });
    expect(page.items.length).toBeGreaterThan(2);
    const row = page.items.find((item) => item.application.status === "open");
    if (row === undefined) throw new Error("No open application");
    expect(Object.keys(row.figures)).toHaveLength(6);

    // A supply date with no full payment yet: the first figure runs to today.
    const today = todayInIndia();
    await recordStage(row.application.id, {
      body: {
        stage_code: "farmer_share",
        occurred_on: today,
        values: { supply: today },
        remark: "Supplied",
      },
      idempotencyKey: "age-1",
    });
    const after = await getAgeing({ ...NONE, q: row.application.number, cursor: null });
    expect(after.items[0]?.figures.today_to_supply).toMatchObject({
      days: 0,
      running: true,
      since: today,
      until: null,
    });
  });

  it("filters by status and refuses a dealer", async () => {
    const cancelled = await getAgeing({ ...NONE, status: "cancelled", cursor: null });
    expect(cancelled.items.every((row) => row.application.status === "cancelled")).toBe(true);
    writeMockRole("dealer");
    await expect(getAgeing({ ...NONE, cursor: null })).rejects.toMatchObject({ status: 403 });
  });
});

describe("[SUBS-010] Subsidy stage report", () => {
  afterEach(reset);

  it("counts open applications by stage, in stage order, with their money", async () => {
    const rows = await getStageReport("open");
    const open = await listApplications({
      status: "open",
      stage: null,
      q: "",
      leadId: null,
      cursor: null,
    });
    expect(rows.reduce((sum, row) => sum + row.count, 0)).toBe(open.items.length);
    expect(rows.map((row) => row.seq)).toEqual(
      [...rows.map((row) => row.seq)].sort((a, b) => a - b),
    );
    expect(rows[0]?.subsidy).toMatch(/^\d+\.\d{2}$/);
  });
});

describe("[SUBS-011] Subsidy supply report", () => {
  afterEach(reset);

  it("splits supplied from not supplied by district, leaving out cancelled ones", async () => {
    const rows = await getSupplyReport(null);
    const live = await listApplications({
      status: null,
      stage: null,
      q: "",
      leadId: null,
      cursor: null,
    });
    const notCancelled = live.items.filter((row) => row.status !== "cancelled").length;
    expect(rows.reduce((sum, row) => sum + row.supplied + row.notSupplied, 0)).toBe(notCancelled);
    expect(rows.some((row) => row.supplied > 0)).toBe(true);
  });
});
