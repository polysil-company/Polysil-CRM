import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { z } from "zod";

import { createLeadFieldErrors } from "@/features/leads/lib/create-lead-errors";
import { ApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockLookupRows } from "@/mocks/data/lookups";
import { MOCK_PARTNERS, MOCK_STAFF } from "@/mocks/data/reference";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  addLeadNote,
  assignLead,
  createLead,
  getLead,
  getLeadStats,
  getLeadTimeline,
  listAssignees,
  listLeads,
  reopenLead,
  searchPartners,
  transitionLead,
} from "./leads.api";
import {
  LEAD_STAGES,
  TIMELINE_PAGE_SIZE,
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
  crops: ["cotton", "groundnut"],
  land_acres: "4.50",
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
    crops: ["cotton"],
    landAcres: " 4.5 ",
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
      crops: ["cotton"],
      land_acres: "4.5",
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
      landAcres: "0",
      crops: Array.from({ length: 11 }, (_, index) => `crop-${String(index)}`),
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
        "Enter the land in acres, e.g. 4.5.",
        "Choose at most 10 crops.",
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

/** A seeded lead whose history runs past one timeline page: lost after many steps. */
function leadWithLongHistory(): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads.find((item) => item.stage === "lost" || item.stage === "won");
  if (lead === undefined) {
    throw new Error("No won or lost lead in the mock database");
  }
  return lead;
}

describe("[LEAD-005] getLeadTimeline", () => {
  afterEach(() => {
    server.events.removeAllListeners();
    resetMockDb();
  });

  it("returns the newest events first, starting with the lead's creation at the end", async () => {
    const lead = firstMockLead();

    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });

    expect(page.items.length).toBeGreaterThan(0);
    const times = page.items.map((event) => Date.parse(event.occurredAt));
    expect([...times].sort((a, b) => b - a)).toEqual(times);
    expect(page.items.at(-1)?.kind).toBe("lead.created");
  });

  it("asks for one page and follows the cursor to older events", async () => {
    const lead = leadWithLongHistory();
    for (let index = 0; index < TIMELINE_PAGE_SIZE; index += 1) {
      await addLeadNote({
        leadId: lead.id,
        body: { note: `Visit ${String(index)}` },
        idempotencyKey: `key-${String(index)}`,
      });
    }
    let sent: URL | undefined;
    server.events.on("request:start", ({ request }) => {
      sent = new URL(request.url);
    });

    const first = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(sent?.searchParams.get("limit")).toBe(String(TIMELINE_PAGE_SIZE));
    expect(first.items).toHaveLength(TIMELINE_PAGE_SIZE);
    expect(first.nextCursor).not.toBeNull();

    const older = await getLeadTimeline({ leadId: lead.id, cursor: first.nextCursor });
    expect(older.items.at(-1)?.kind).toBe("lead.created");
    expect(older.items.map((event) => event.id)).not.toContain(first.items[0]?.id);
  });

  it("keeps an event with an empty actor name, and hides no event for its payload", async () => {
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({
          data: [
            {
              id: "e1",
              kind: "quotation.sent",
              occurred_at: "2026-09-20T10:00:00+00:00",
              actor: { id: "u1", full_name: "" },
              payload: { quotation_no: 7 },
            },
            { id: "e2", kind: "lead.created", occurred_at: "2026-09-19T10:00:00+00:00" },
          ],
          meta: { limit: 20 },
        }),
      ),
    );

    const page = await getLeadTimeline({ leadId: "lead-x", cursor: null });

    expect(page.items.map((event) => event.id)).toEqual(["e1", "e2"]);
    expect(page.items[0]?.actor).toEqual({ id: "u1", name: null });
    expect(page.items[1]?.actor).toBeNull();
    expect(page.nextCursor).toBeNull();
  });

  it("leaves out one broken event and keeps the rest", async () => {
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({
          data: [
            { id: "e1", kind: "lead.created", occurred_at: "2026-09-19T10:00:00+00:00" },
            { id: "e2", kind: "lead.note_added", occurred_at: "yesterday" },
          ],
          meta: { limit: 20, next_cursor: null },
        }),
      ),
    );

    const page = await getLeadTimeline({ leadId: "lead-x", cursor: null });

    expect(page.items.map((event) => event.id)).toEqual(["e1"]);
    expect(page.skipped).toBe(1);
  });

  it("reports a lead outside the caller's scope as 404", async () => {
    await expect(getLeadTimeline({ leadId: "lead-missing", cursor: null })).rejects.toMatchObject({
      kind: "http",
      status: 404,
      dataId: "LEAD-005",
    });
  });
});

describe("[LEAD-006] addLeadNote", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("adds the note as the newest timeline event", async () => {
    const lead = firstMockLead();

    const event = await addLeadNote({
      leadId: lead.id,
      body: { note: "Farmer wants a site visit on Monday" },
      idempotencyKey: "note-1",
    });

    expect(event).toMatchObject({
      kind: "lead.note_added",
      payload: { note: "Farmer wants a site visit on Monday" },
    });
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items[0]?.id).toBe(event.id);
  });

  it("replays a retry with the same key instead of adding the note twice", async () => {
    const lead = firstMockLead();
    const input = { leadId: lead.id, body: { note: "Called twice?" }, idempotencyKey: "note-2" };

    const first = await addLeadNote(input);
    const retry = await addLeadNote(input);

    expect(retry.id).toBe(first.id);
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items.filter((item) => item.kind === "lead.note_added")).toHaveLength(1);
  });

  it("refuses a key reused for a different note with 409", async () => {
    const lead = firstMockLead();
    await addLeadNote({ leadId: lead.id, body: { note: "First" }, idempotencyKey: "note-3" });

    await expect(
      addLeadNote({ leadId: lead.id, body: { note: "Second" }, idempotencyKey: "note-3" }),
    ).rejects.toMatchObject({ kind: "http", status: 409, dataId: "LEAD-006" });
  });

  it("reports a blank note as a field error on note", async () => {
    const lead = firstMockLead();

    const error: unknown = await addLeadNote({
      leadId: lead.id,
      body: { note: "   " },
      idempotencyKey: "note-4",
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, details: { fields: { note: expect.any(String) } } });
  });
});

describe("[LEAD-007] transitionLead and reopenLead", () => {
  afterEach(() => {
    resetMockDb();
  });

  function leadAt(stage: (typeof mockDb.leads)[number]["stage"]): (typeof mockDb.leads)[number] {
    const lead = mockDb.leads.find((item) => item.stage === stage);
    if (lead === undefined) {
      throw new Error(`No ${stage} lead in the mock database`);
    }
    return lead;
  }

  const move = (to: "contacted" | "qualified" | "won" | "quoted", expected: string) => ({
    to_stage: to,
    lost_reason_id: null,
    lost_note: null,
    expected_stage: z.enum(LEAD_STAGES).parse(expected),
  });

  it("moves a new lead to contacted and records it on the timeline", async () => {
    const lead = leadAt("new");

    const moved = await transitionLead({
      leadId: lead.id,
      body: move("contacted", "new"),
      idempotencyKey: "t-1",
    });

    expect(moved.stage).toBe("contacted");
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items[0]).toMatchObject({
      kind: "lead.stage_changed",
      payload: { from: "new", to: "contacted" },
    });
    expect(page.items.filter((item) => item.kind === "lead.stage_changed")).toHaveLength(1);
  });

  it("refuses to act on a stale view with 409 stage_changed and the current stage", async () => {
    const lead = leadAt("contacted");

    await expect(
      transitionLead({ leadId: lead.id, body: move("contacted", "new"), idempotencyKey: "t-2" }),
    ).rejects.toMatchObject({
      status: 409,
      code: "stage_changed",
      details: { fields: { stage: "contacted" } },
    });
  });

  it("refuses quoted from here, and won without an accepted quotation", async () => {
    await expect(
      transitionLead({
        leadId: leadAt("qualified").id,
        body: move("quoted", "qualified"),
        idempotencyKey: "t-3",
      }),
    ).rejects.toMatchObject({ status: 422, code: "quotation_required" });
    await expect(
      transitionLead({
        leadId: leadAt("quoted").id,
        body: move("won", "quoted"),
        idempotencyKey: "t-4",
      }),
    ).rejects.toMatchObject({ status: 422, code: "quotation_required" });
  });

  it("needs an active lost reason to mark a lead lost", async () => {
    const lead = leadAt("contacted");

    await expect(
      transitionLead({
        leadId: lead.id,
        body: {
          to_stage: "lost",
          lost_reason_id: null,
          lost_note: null,
          expected_stage: "contacted",
        },
        idempotencyKey: "t-5",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { lost_reason_id: expect.any(String) } },
    });
  });

  it("reopens a lost lead at the stage it was lost from", async () => {
    const lead = leadAt("contacted");
    const reason = mockLookupRows("lost-reasons")[0];
    await transitionLead({
      leadId: lead.id,
      body: {
        to_stage: "lost",
        lost_reason_id: reason?.id ?? null,
        lost_note: "Went quiet",
        expected_stage: "contacted",
      },
      idempotencyKey: "t-6",
    });

    const reopened = await reopenLead({
      leadId: lead.id,
      body: { note: "Called back" },
      idempotencyKey: "r-1",
    });

    expect(reopened).toMatchObject({ stage: "contacted", lostReason: null, reopenCount: 1 });
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items[0]).toMatchObject({
      kind: "lead.reopened",
      payload: { to: "contacted", note: "Called back" },
    });
  });

  it("reopens only a lost lead", async () => {
    await expect(
      reopenLead({ leadId: leadAt("won").id, body: { note: null }, idempotencyKey: "r-2" }),
    ).rejects.toMatchObject({ status: 422, code: "stage_terminal" });
  });

  it("replays a retried move instead of moving the lead twice", async () => {
    const lead = leadAt("new");
    const input = { leadId: lead.id, body: move("contacted", "new"), idempotencyKey: "t-7" };

    await transitionLead(input);
    const retry = await transitionLead(input);

    expect(retry.stage).toBe("contacted");
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items.filter((item) => item.kind === "lead.stage_changed")).toHaveLength(1);
  });
});

describe("[LEAD-008] assignment", () => {
  afterEach(() => {
    writeMockRole("state_manager");
    resetMockDb();
  });

  function openLead(): (typeof mockDb.leads)[number] {
    const lead = mockDb.leads.find(
      (item) => item.stage === "contacted" && item.merged_into === null,
    );
    if (lead === undefined) {
      throw new Error("No open lead in the mock database");
    }
    return lead;
  }

  it("lists the people a manager may make the owner", async () => {
    const people = await listAssignees();

    expect(people.map((person) => person.name)).toEqual(
      MOCK_STAFF.map((person) => person.full_name),
    );
  });

  it("lists nobody for a role that may not set owners", async () => {
    writeMockRole("employee");

    await expect(listAssignees()).resolves.toEqual([]);
  });

  it("searches partners by name, with their type and district", async () => {
    const partners = await searchPartners("khodiyar");

    expect(partners).toEqual([
      expect.objectContaining({
        name: "Khodiyar Irrigation",
        partnerType: "dealer",
        territoryName: "Rajkot",
      }),
    ]);
  });

  it("sets the owner and the partner, and records the assignment", async () => {
    const lead = openLead();
    const person = MOCK_STAFF[2];
    const partner = MOCK_PARTNERS[0];

    const assigned = await assignLead({
      leadId: lead.id,
      body: { owner_user_id: person?.id ?? null, assigned_partner_id: partner?.id ?? null },
      idempotencyKey: "a-1",
    });

    expect(assigned.owner).toEqual({ id: person?.id, name: person?.full_name });
    expect(assigned.channelPartner?.name).toBe(partner?.name);
    const page = await getLeadTimeline({ leadId: lead.id, cursor: null });
    expect(page.items[0]).toMatchObject({
      kind: "lead.assigned",
      payload: { owner_user_id: person?.id, assigned_partner_id: partner?.id },
    });
  });

  it("leaves a field it was not sent alone, and clears one sent as null", async () => {
    const lead = openLead();
    const ownerBefore = lead.owner;

    const assigned = await assignLead({
      leadId: lead.id,
      body: { assigned_partner_id: null },
      idempotencyKey: "a-2",
    });

    expect(assigned.channelPartner).toBeNull();
    expect(assigned.owner?.id).toBe(ownerBefore?.id);
  });

  it("refuses an owner the caller may not assign, on owner_user_id", async () => {
    writeMockRole("employee");

    await expect(
      assignLead({
        leadId: openLead().id,
        body: { owner_user_id: MOCK_STAFF[1]?.id ?? null },
        idempotencyKey: "a-3",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { owner_user_id: expect.any(String) } },
    });
  });

  it("refuses to reassign a closed lead", async () => {
    const won = mockDb.leads.find((item) => item.stage === "won");

    await expect(
      assignLead({
        leadId: won?.id ?? "",
        body: { assigned_partner_id: null },
        idempotencyKey: "a-4",
      }),
    ).rejects.toMatchObject({ status: 422, code: "stage_terminal" });
  });
});
