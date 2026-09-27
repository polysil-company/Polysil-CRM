import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { createLeadFieldErrors } from "@/features/leads/lib/create-lead-errors";
import { ApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import { createLead, getLead, getLeadStats, listLeads } from "./leads.api";
import {
  createLeadFormSchema,
  createLeadRequestSchema,
  type CreateLeadFormValues,
  type CreateLeadRequest,
  type LeadListParams,
} from "./leads.schemas";

const FIRST_PAGE: LeadListParams = {
  cursor: null,
  pageSize: 25,
  sort: "createdAt",
  order: "desc",
  q: "",
  stage: [],
  source: null,
  type: null,
};

function territoryNamed(name: string): (typeof MOCK_TERRITORIES)[number] {
  const territory = MOCK_TERRITORIES.find((candidate) => candidate.name === name);
  if (territory === undefined) {
    throw new Error(`No mock territory named ${name}`);
  }
  return territory;
}

const NEW_LEAD: CreateLeadRequest = {
  farmer_name: "Test Farmer",
  mobile: "+919000000001",
  email: null,
  territory_id: territoryNamed("Gondal").id,
  village: null,
  inquiry_type: "subsidised",
  mis_system: "drip",
  source: null,
  estimated_value: "150000",
  note: null,
};

function firstMockLead(): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads[0];
  if (lead === undefined) {
    throw new Error("Mock database is empty");
  }
  return lead;
}

/** Leads the default list shows: every stage except merged. */
function visibleMockLeads(): typeof mockDb.leads {
  return mockDb.leads.filter((lead) => lead.stage !== "merged");
}

describe("[LEAD-001] listLeads", () => {
  it("returns the first page, newest first, with the matching total", async () => {
    const result = await listLeads(FIRST_PAGE);

    expect(result.items).toHaveLength(25);
    expect(result.total).toBe(visibleMockLeads().length);
    expect(result.totalCapped).toBe(false);
    expect(result.nextCursor).not.toBeNull();
    const created = result.items.map((lead) => Date.parse(lead.createdAt));
    expect(created).toEqual([...created].sort((a, b) => b - a));
  });

  it("leaves out a lead that breaks the contract and keeps the rest of the page", async () => {
    const good = firstMockLead();
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({
          data: [good, { ...good, id: "broken-lead", mobile: null }],
          meta: { limit: 25, next_cursor: null, total: 2 },
        }),
      ),
    );

    const result = await listLeads(FIRST_PAGE);

    expect(result.items.map((lead) => lead.id)).toEqual([good.id]);
    expect(result.skipped).toBe(1);
  });

  it("fails as a contract violation when no lead in the page matches", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({
          data: [{ id: 42 }],
          meta: { limit: 25, next_cursor: null, total: 1 },
        }),
      ),
    );

    await expect(listLeads(FIRST_PAGE)).rejects.toMatchObject({
      code: "CONTRACT_VIOLATION",
      dataId: "LEAD-001",
    });
  });

  it("asks for the total, the page size and the order it wants", async () => {
    let sent: URL | undefined;
    server.use(
      http.get(buildApiUrl("/leads"), ({ request }) => {
        sent = new URL(request.url);
        return HttpResponse.json({ data: [], meta: { limit: 50, next_cursor: null, total: 0 } });
      }),
    );

    await listLeads({ ...FIRST_PAGE, pageSize: 50, sort: "customerName", order: "asc" });

    expect(sent?.searchParams.get("include_total")).toBe("true");
    expect(sent?.searchParams.get("limit")).toBe("50");
    expect(sent?.searchParams.get("sort")).toBe("farmer_name");
    expect(sent?.searchParams.get("order")).toBe("asc");
    expect(sent?.searchParams.has("cursor")).toBe(false);
    expect(sent?.searchParams.has("stage")).toBe(false);
  });

  it("moves through pages with the cursor, and says when there are no more", async () => {
    const page1 = await listLeads(FIRST_PAGE);
    const page2 = await listLeads({ ...FIRST_PAGE, cursor: page1.nextCursor });

    expect(page2.items[0]?.id).not.toBe(page1.items[0]?.id);
    expect(page2.total).toBe(page1.total);

    const everything = await listLeads({ ...FIRST_PAGE, pageSize: 100 });
    const last = await listLeads({ ...FIRST_PAGE, pageSize: 100, cursor: everything.nextCursor });
    expect(last.nextCursor).toBeNull();
    expect(everything.items.length + last.items.length).toBe(visibleMockLeads().length);
  });

  it("filters by several stages, and shows merged leads only when asked", async () => {
    const closed = await listLeads({ ...FIRST_PAGE, stage: ["won", "lost"], pageSize: 100 });
    expect(closed.items.length).toBeGreaterThan(0);
    expect(closed.items.every((lead) => lead.stage === "won" || lead.stage === "lost")).toBe(true);

    const everyone = await listLeads({ ...FIRST_PAGE, pageSize: 100 });
    expect(everyone.items.some((lead) => lead.stage === "merged")).toBe(false);

    const merged = await listLeads({ ...FIRST_PAGE, stage: ["merged"], pageSize: 100 });
    expect(merged.items.every((lead) => lead.stage === "merged")).toBe(true);
  });

  it("filters by one source and one inquiry type", async () => {
    const result = await listLeads({
      ...FIRST_PAGE,
      source: "whatsapp",
      type: "subsidised",
      pageSize: 100,
    });

    expect(result.items.length).toBeGreaterThan(0);
    expect(
      result.items.every((lead) => lead.source === "whatsapp" && lead.type === "subsidised"),
    ).toBe(true);
  });

  it("finds a lead by its inquiry number or part of its mobile number", async () => {
    const target = firstMockLead();

    const byNumber = await listLeads({ ...FIRST_PAGE, q: target.inquiry_no });
    expect(byNumber.items.map((lead) => lead.id)).toContain(target.id);

    const byMobile = await listLeads({ ...FIRST_PAGE, q: target.mobile.slice(-6) });
    expect(byMobile.items.map((lead) => lead.id)).toContain(target.id);
  });

  it("reads a capped total as a lower bound", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({
          data: [],
          meta: { limit: 25, next_cursor: "b2Zmc2V0OjI1", total: 1000, total_capped: true },
        }),
      ),
    );

    const result = await listLeads(FIRST_PAGE);

    expect(result).toMatchObject({ total: 1000, totalCapped: true, nextCursor: "b2Zmc2V0OjI1" });
  });

  it("fails with the backend's field error for a cursor it cannot read", async () => {
    const error: unknown = await listLeads({ ...FIRST_PAGE, cursor: "not-a-cursor" }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      details: { fields: { cursor: expect.any(String) } },
    });
  });
});

describe("[LEAD-003] getLead", () => {
  it("returns one lead in the screens' shape, with its duplicate links", async () => {
    const target = mockDb.leads.find((lead) => (lead.duplicates ?? []).length > 0);
    if (target === undefined) {
      throw new Error("The mock has no flagged duplicates");
    }

    const lead = await getLead(target.id);

    expect(lead).toMatchObject({
      id: target.id,
      code: target.inquiry_no,
      customerName: target.farmer_name,
      phone: target.mobile,
    });
    expect(lead.duplicates[0]).toMatchObject({ signal: "mobile", state: "pending" });
  });

  it("fails with a 404 ApiError for an unknown lead", async () => {
    await expect(getLead("lead-missing")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      dataId: "LEAD-003",
    });
  });
});

describe("[LEAD-004] getLeadStats", () => {
  it("counts the leads the list would show, by stage, priority and owner", async () => {
    const visible = visibleMockLeads();

    const stats = await getLeadStats();

    expect(stats.total).toBe(visible.length);
    expect(stats.byStage.merged).toBe(0);
    expect(stats.byStage.new).toBe(visible.filter((lead) => lead.stage === "new").length);
    expect(stats.byPriority.hot).toBe(visible.filter((lead) => lead.priority === "hot").length);
    expect(stats.unassigned).toBe(visible.filter((lead) => lead.owner === null).length);
  });

  it("reads the bare stats object, not a { data } envelope", async () => {
    server.use(
      http.get(buildApiUrl("/leads/stats"), () =>
        HttpResponse.json({
          total: 1234,
          by_stage: { new: 1000, contacted: 234 },
          by_priority: { hot: 10, warm: 20, cold: 30 },
          unassigned: 7,
        }),
      ),
    );

    await expect(getLeadStats()).resolves.toEqual({
      total: 1234,
      byStage: { new: 1000, contacted: 234 },
      byPriority: { hot: 10, warm: 20, cold: 30 },
      unassigned: 7,
    });
  });

  it("reports a stats body that breaks the contract", async () => {
    server.use(
      http.get(buildApiUrl("/leads/stats"), () => HttpResponse.json({ data: { total: 12 } })),
    );

    await expect(getLeadStats()).rejects.toMatchObject({
      kind: "contract",
      code: "CONTRACT_VIOLATION",
      dataId: "LEAD-004",
    });
  });
});

describe("[LEAD-002] createLead", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("creates a new lead that appears first in the list", async () => {
    const lead = await createLead({ body: NEW_LEAD, idempotencyKey: "key-create" });

    expect(lead).toMatchObject({
      customerName: "Test Farmer",
      stage: "new",
      source: "employee",
      estimatedValue: "150000.00",
      territory: { name: "Gondal", level: "taluka" },
    });
    const list = await listLeads(FIRST_PAGE);
    expect(list.items[0]?.id).toBe(lead.id);
  });

  it("flags a duplicate mobile number instead of refusing it", async () => {
    const existing = firstMockLead();

    const lead = await createLead({
      body: { ...NEW_LEAD, mobile: existing.mobile },
      idempotencyKey: "key-duplicate",
    });

    expect(lead.duplicates).toEqual([
      expect.objectContaining({ leadId: existing.id, signal: "mobile", state: "pending" }),
    ]);
  });

  it("replays a retry with the same key instead of creating a second lead", async () => {
    const before = mockDb.leads.length;

    const first = await createLead({ body: NEW_LEAD, idempotencyKey: "key-retry" });
    const retry = await createLead({ body: NEW_LEAD, idempotencyKey: "key-retry" });

    expect(retry.id).toBe(first.id);
    expect(mockDb.leads).toHaveLength(before + 1);
  });

  it("refuses the same key with different details", async () => {
    await createLead({ body: NEW_LEAD, idempotencyKey: "key-reused" });

    await expect(
      createLead({
        body: { ...NEW_LEAD, farmer_name: "Someone Else" },
        idempotencyKey: "key-reused",
      }),
    ).rejects.toMatchObject({ status: 409, code: "idempotency_key_reused" });
  });

  it("puts a territory no office covers on the territory field, in plain words", async () => {
    const error: unknown = await createLead({
      body: { ...NEW_LEAD, territory_id: territoryNamed("Dang").id },
      idempotencyKey: "key-dang",
    }).catch((caught: unknown) => caught);

    expect(error).toMatchObject({ status: 422, code: "territory_without_org_unit" });
    expect(createLeadFieldErrors(error)).toEqual([
      {
        field: "territory",
        message:
          "No Polysil office covers this place yet. Choose the taluka or district around it.",
      },
    ]);
  });
});

describe("[LEAD-002] New lead form schema", () => {
  const typed: CreateLeadFormValues = {
    customerName: "  Ramesh Patel ",
    phone: "98123 45678",
    email: "",
    territory: { id: territoryNamed("Gondal").id, name: "Gondal", level: "taluka" },
    village: " Virpur ",
    type: "commercial",
    misSystem: "drip",
    source: null,
    estimatedValue: "125000.50",
    note: "",
  };

  it("turns what people type into the backend's request body", () => {
    const body = createLeadFormSchema.parse(typed);

    expect(body).toEqual({
      farmer_name: "Ramesh Patel",
      mobile: "+919812345678",
      email: null,
      territory_id: territoryNamed("Gondal").id,
      village: "Virpur",
      inquiry_type: "commercial",
      mis_system: "drip",
      source: null,
      estimated_value: "125000.50",
      note: null,
    });
    expect(createLeadRequestSchema.safeParse(body).success).toBe(true);
  });

  it("explains every invalid or missing field", () => {
    const result = createLeadFormSchema.safeParse({
      ...typed,
      customerName: " ",
      phone: "12345",
      email: "ramesh@",
      territory: null,
      misSystem: undefined,
      estimatedValue: "1,25,000",
    });

    expect(result.success).toBe(false);
    const messages = result.success ? [] : result.error.issues.map((issue) => issue.message);
    expect(messages).toEqual(
      expect.arrayContaining([
        "Enter the farmer's name.",
        "Enter a 10-digit Indian mobile number.",
        "Enter an email like name@example.com, or leave it empty.",
        "Choose where the farmer is.",
        "Choose the irrigation system.",
        "Enter an amount in rupees, e.g. 125000.",
      ]),
    );
  });
});

describe("[LEAD-002] createLeadFieldErrors", () => {
  function validationError(fields: Record<string, string>, code = "validation_error"): ApiError {
    return new ApiError({
      kind: "http",
      message: "Some fields need correcting.",
      dataId: "LEAD-002",
      requestId: "req-1",
      method: "POST",
      path: "/leads",
      status: 422,
      code,
      details: { fields },
    });
  }

  it("maps the backend's field paths onto the form, first error per field", () => {
    const errors = createLeadFieldErrors(
      validationError({
        mobile: "mobile must be E.164 digits",
        "estimated_value.float": "input should be a valid number",
        "estimated_value.constrained-str": "string should match pattern",
        unknown_field: "ignored",
      }),
    );

    expect(errors).toEqual([
      { field: "phone", message: "Mobile must be E.164 digits." },
      { field: "estimatedValue", message: "Input should be a valid number." },
    ]);
  });

  it("returns nothing for errors that are not field validation failures", () => {
    expect(createLeadFieldErrors(new Error("offline"))).toEqual([]);
  });
});
