import { afterEach, describe, expect, it } from "vitest";

import { mockDb, resetMockDb } from "@/mocks/db";

import { createLead, getLead, getLeadSummary, listLeads } from "./leads.api";
import {
  createLeadFormSchema,
  createLeadRequestSchema,
  LEAD_SOURCES,
  LEAD_STATUSES,
  type CreateLeadRequest,
  type LeadListParams,
} from "./leads.schemas";

const FIRST_PAGE: LeadListParams = {
  page: 1,
  pageSize: 25,
  sort: "createdAt",
  order: "desc",
  q: "",
  status: [],
  source: [],
  type: [],
};

const NEW_LEAD: CreateLeadRequest = {
  customerName: "Test Farmer",
  phone: "+919000000001",
  village: "",
  district: "Vadodara",
  state: "Gujarat",
  source: "employee",
  type: "subsidised",
  estimatedValue: 150_000,
  notes: "",
};

function firstMockLead(): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads[0];
  if (lead === undefined) {
    throw new Error("Mock database is empty");
  }
  return lead;
}

describe("[LEAD-001] listLeads", () => {
  it("returns the first page, newest first", async () => {
    const result = await listLeads(FIRST_PAGE);

    expect(result.items).toHaveLength(25);
    expect(result.total).toBe(mockDb.leads.length);
    const created = result.items.map((lead) => Date.parse(lead.createdAt));
    expect(created).toEqual([...created].sort((a, b) => b - a));
  });

  it("filters by status and finds a lead by its code", async () => {
    const won = await listLeads({ ...FIRST_PAGE, status: ["won"], pageSize: 100 });
    expect(won.items.length).toBeGreaterThan(0);
    expect(won.items.every((lead) => lead.status === "won")).toBe(true);

    const target = firstMockLead();
    const found = await listLeads({ ...FIRST_PAGE, q: target.code });
    expect(found.items.map((lead) => lead.id)).toContain(target.id);
  });

  it("paginates on the server", async () => {
    const [page1, page2] = await Promise.all([
      listLeads(FIRST_PAGE),
      listLeads({ ...FIRST_PAGE, page: 2 }),
    ]);

    expect(page2.page).toBe(2);
    expect(page2.items[0]?.id).not.toBe(page1.items[0]?.id);
  });
});

describe("[LEAD-003] getLead", () => {
  it("returns one lead", async () => {
    const target = firstMockLead();
    await expect(getLead(target.id)).resolves.toMatchObject({ id: target.id, code: target.code });
  });

  it("fails with a 404 ApiError for an unknown lead", async () => {
    await expect(getLead("lead-missing")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      dataId: "LEAD-003",
    });
  });
});

describe("[LEAD-002] createLead", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("creates a lead that appears first in the list", async () => {
    const lead = await createLead(NEW_LEAD);
    expect(lead).toMatchObject({ customerName: "Test Farmer", status: "new", village: null });

    const list = await listLeads(FIRST_PAGE);
    expect(list.items[0]?.id).toBe(lead.id);
  });

  it("rejects a duplicate phone number with a field error", async () => {
    const existing = firstMockLead();

    await expect(createLead({ ...NEW_LEAD, phone: existing.phone })).rejects.toMatchObject({
      kind: "http",
      status: 422,
      code: "DUPLICATE_PHONE",
      details: { fields: { phone: expect.any(String) } },
    });
  });
});

describe("[LEAD-002] New lead form schema", () => {
  const typed = {
    customerName: "  Ramesh Patel ",
    phone: "98123 45678",
    village: "",
    district: "Vadodara",
    state: "Gujarat",
    source: "whatsapp",
    type: "commercial",
    estimatedValue: "125000.50",
    notes: "",
  };

  it("turns what people type into a valid request body", () => {
    const result = createLeadFormSchema.parse(typed);

    expect(result).toMatchObject({
      customerName: "Ramesh Patel",
      phone: "+919812345678",
      estimatedValue: 125_000.5,
    });
    expect(createLeadRequestSchema.safeParse(result).success).toBe(true);
  });

  it("treats an empty amount as unknown", () => {
    expect(createLeadFormSchema.parse({ ...typed, estimatedValue: "" }).estimatedValue).toBeNull();
  });

  it("explains every invalid field", () => {
    const result = createLeadFormSchema.safeParse({
      ...typed,
      customerName: "R",
      phone: "12345",
      estimatedValue: "1,25,000",
      source: undefined,
    });

    expect(result.success).toBe(false);
    const messages = result.success ? [] : result.error.issues.map((issue) => issue.message);
    expect(messages).toEqual(
      expect.arrayContaining([
        "Enter the customer's full name.",
        "Enter a 10-digit Indian mobile number.",
        "Enter an amount in rupees, e.g. 125000.",
        "Choose where this lead came from.",
      ]),
    );
  });
});

describe("[LEAD-004] getLeadSummary", () => {
  it("counts every lead exactly once in each breakdown", async () => {
    const summary = await getLeadSummary();
    const sum = (counts: Record<string, number>): number =>
      Object.values(counts).reduce((a, b) => a + b, 0);

    expect(summary.total).toBe(mockDb.leads.length);
    expect(sum(summary.byStatus)).toBe(summary.total);
    expect(sum(summary.bySource)).toBe(summary.total);
    expect(Object.keys(summary.byStatus)).toEqual([...LEAD_STATUSES]);
    expect(Object.keys(summary.bySource)).toEqual([...LEAD_SOURCES]);
  });
});
