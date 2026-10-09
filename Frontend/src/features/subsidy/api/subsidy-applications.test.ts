import { afterEach, describe, expect, it } from "vitest";

import type { LeadWire } from "@/features/leads/api/leads.schemas";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  cancelApplication,
  createApplication,
  getApplication,
  getStoredCalculation,
  listApplications,
  listStageDefs,
  listStageEntries,
  recordStage,
} from "./subsidy-applications.api";
import type { CalculateRequest } from "./subsidy.schemas";

const ALL = { status: null, stage: null, q: "", leadId: null } as const;

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

/** A subsidised drip lead that is qualified and has no application yet. */
function forwardableLead(): LeadWire {
  const lead = mockDb.leads.find(
    (item) => item.inquiry_type !== "industrial" && item.stage === "qualified",
  );
  if (lead === undefined) throw new Error("No qualified lead in the seed");
  lead.inquiry_type = "subsidised";
  lead.mis_system = "drip";
  return lead;
}

const CALCULATION: CalculateRequest = {
  system_type: "drip",
  crops: [
    {
      crop: "Mango",
      inter_crop: null,
      area: "1.500",
      crop_spacing: "",
      lateral_spacing: "5.00",
      lines: [{ description: "Lateral", uom: "Mtr.", rate: "12.50", qty: "3000" }],
    },
  ],
  head_lines: [],
};

describe("[SUBS-004] Start a subsidy application", () => {
  afterEach(reset);

  it("forwards a subsidised lead: stage 4 today, the lead won, the calculation stored", async () => {
    const lead = forwardableLead();
    const made = await createApplication({
      body: {
        lead_id: lead.id,
        category_code: "small_farmer",
        calculation: CALCULATION,
        survey_no: "112/2",
      },
      idempotencyKey: "a-1",
    });
    expect(made).toMatchObject({
      status: "open",
      surveyNo: "112/2",
      stage: { seq: 4, code: "application_in_process", since: todayInIndia() },
      category: { code: "small_farmer" },
      lead: { id: lead.id },
    });
    expect(made.figures.subsidy).toMatch(/^\d+\.\d{2}$/);
    expect(lead.stage).toBe("won");
    expect((await getStoredCalculation(made.id)).crops[0]?.crop).toBe("Mango");

    // The same key and body answer the same application.
    const again = await createApplication({
      body: {
        lead_id: lead.id,
        category_code: "small_farmer",
        calculation: CALCULATION,
        survey_no: "112/2",
      },
      idempotencyKey: "a-1",
    });
    expect(again.id).toBe(made.id);
  });

  it("refuses a lead that isn't subsidised, a second application, and a category that doesn't apply", async () => {
    const lead = forwardableLead();
    lead.inquiry_type = "commercial";
    const body = {
      lead_id: lead.id,
      category_code: "small_farmer",
      calculation: CALCULATION,
      survey_no: null,
    };
    await expect(createApplication({ body, idempotencyKey: "a-2" })).rejects.toMatchObject({
      status: 422,
      code: "lead_not_subsidised",
    });

    lead.inquiry_type = "subsidised";
    await expect(
      createApplication({
        body: {
          ...body,
          category_code: "seven_year_small",
          calculation: {
            ...CALCULATION,
            crops: CALCULATION.crops.map((crop) => ({ ...crop, area: "6.000" })),
          },
        },
        idempotencyKey: "a-3",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { category_code: expect.any(String) } },
    });

    await createApplication({ body, idempotencyKey: "a-4" });
    await expect(createApplication({ body, idempotencyKey: "a-5" })).rejects.toMatchObject({
      status: 422,
      code: "already_forwarded",
    });
  });

  it("names a calculation's mistake under calculation.", async () => {
    const lead = forwardableLead();
    await expect(
      createApplication({
        body: {
          lead_id: lead.id,
          category_code: "small_farmer",
          calculation: {
            ...CALCULATION,
            crops: CALCULATION.crops.map((crop) => ({ ...crop, crop: "Saffron" })),
          },
          survey_no: null,
        },
        idempotencyKey: "a-6",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { "calculation.crops[0].crop": "not in the crop table" } },
    });
  });
});

describe("[SUBS-005] The applications worklist", () => {
  afterEach(reset);

  it("lists newest first and filters by status, stage and search", async () => {
    const page = await listApplications({ ...ALL, cursor: null });
    expect(page.items.length).toBeGreaterThan(2);
    const cancelled = await listApplications({ ...ALL, status: "cancelled", cursor: null });
    expect(cancelled.items.every((row) => row.status === "cancelled")).toBe(true);
    const first = page.items[0];
    if (first === undefined) throw new Error("No application");
    const found = await listApplications({ ...ALL, q: first.farmerName, cursor: null });
    expect(found.items.map((row) => row.id)).toContain(first.id);
    const byLead = await listApplications({ ...ALL, leadId: first.lead.id, cursor: null });
    expect(byLead.items.map((row) => row.id)).toEqual([first.id]);
  });

  it("refuses a dealer", async () => {
    writeMockRole("dealer");
    await expect(listApplications({ ...ALL, cursor: null })).rejects.toMatchObject({ status: 403 });
  });
});

describe("[SUBS-006] Stages and cancel", () => {
  afterEach(reset);

  async function fresh(): Promise<string> {
    const lead = forwardableLead();
    const made = await createApplication({
      body: {
        lead_id: lead.id,
        category_code: "small_farmer",
        calculation: CALCULATION,
        survey_no: null,
      },
      idempotencyKey: `s-${lead.id}`,
    });
    return made.id;
  }

  it("records a stage with its values, sets the Reg. No., and wants a remark going back", async () => {
    const id = await fresh();
    const stages = await listStageDefs(null);
    expect(stages.map((stage) => stage.seq)).toEqual([
      4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
    ]);

    const today = todayInIndia();
    const withReg = await recordStage(id, {
      body: {
        stage_code: "application_in_process",
        occurred_on: today,
        values: { reg_no: "GGRC/24/777", app_inward: today },
        remark: "Reg. No. from the portal",
      },
      idempotencyKey: "st-1",
    });
    expect(withReg.regNo).toBe("GGRC/24/777");

    const forward = await recordStage(id, {
      body: { stage_code: "technical_in_process", occurred_on: today, values: {}, remark: null },
      idempotencyKey: "st-2",
    });
    expect(forward.stage.code).toBe("technical_in_process");

    await expect(
      recordStage(id, {
        body: {
          stage_code: "application_in_process",
          occurred_on: today,
          values: {},
          remark: null,
        },
        idempotencyKey: "st-3",
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { remark: expect.any(String) } } });

    await expect(
      recordStage(id, {
        body: {
          stage_code: "farmer_share",
          occurred_on: today,
          values: { farmer_share_amt: "1250.505" },
          remark: null,
        },
        idempotencyKey: "st-4",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { "values.farmer_share_amt": expect.any(String) } },
    });

    const entries = await listStageEntries(id);
    expect(entries.map((entry) => entry.stage.code)).toEqual([
      "application_in_process",
      "application_in_process",
      "technical_in_process",
    ]);
  });

  it("closes itself once every stage-16 amount has its stage-17 date", async () => {
    const id = await fresh();
    const today = todayInIndia();
    await recordStage(id, {
      body: {
        stage_code: "fp_cleared_pay_pending",
        occurred_on: today,
        values: { pfms_amt: "50000.00", state_share_amt: "12000.00" },
        remark: null,
      },
      idempotencyKey: "c-1",
    });
    const half = await recordStage(id, {
      body: {
        stage_code: "payment_received",
        occurred_on: today,
        values: { pfms_received: today },
        remark: null,
      },
      idempotencyKey: "c-2",
    });
    expect(half.status).toBe("open");
    const closed = await recordStage(id, {
      body: {
        stage_code: "payment_received",
        occurred_on: today,
        values: { state_share_received: today },
        remark: "State share in",
      },
      idempotencyKey: "c-3",
    });
    expect(closed).toMatchObject({ status: "full_fp_received", closedOn: today });
    await expect(
      recordStage(id, {
        body: { stage_code: "payment_received", occurred_on: today, values: {}, remark: "again" },
        idempotencyKey: "c-4",
      }),
    ).rejects.toMatchObject({ status: 409, code: "status_changed" });
  });

  it("cancels with a reason, which frees the lead; a view-only user can't", async () => {
    const id = await fresh();
    writeMockRole("regional_manager");
    await expect(
      cancelApplication(id, { body: { reason: "Farmer withdrew" }, idempotencyKey: "x-1" }),
    ).rejects.toMatchObject({ status: 403 });
    writeMockRole("admin");
    const cancelled = await cancelApplication(id, {
      body: { reason: "Farmer withdrew" },
      idempotencyKey: "x-2",
    });
    expect(cancelled).toMatchObject({
      status: "cancelled",
      cancellation: { reason: "Farmer withdrew" },
    });
    expect((await getApplication(id)).status).toBe("cancelled");
  });
});
