import { http, HttpResponse } from "msw";

import {
  addLeadNoteRequestSchema,
  assignLeadRequestSchema,
  createLeadRequestSchema,
  reopenLeadRequestSchema,
  transitionLeadRequestSchema,
  LEAD_AREA_LEVELS,
  LEAD_STAGES,
  type CreateLeadRequest,
  type LeadAreaLevel,
  type LeadAreaWire,
  type LeadPageWire,
  type LeadResponseWire,
  type LeadStage,
  type AssigneeListWire,
  type LeadStatsWire,
  type TimelinePageWire,
  type LeadWire,
  type DuplicatePageWire,
  type DuplicatePairWire,
} from "@/features/leads/api/leads.schemas";
import { summarizeSchemaIssues } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockLookupRows } from "@/mocks/data/lookups";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, MOCK_PARTNERS, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import {
  findMockTerritory,
  MOCK_TERRITORIES,
  mockOfficeFor,
  mockTerritoryLineage,
  toTerritoryRef,
} from "@/mocks/data/territories";
import { newestFirst } from "@/mocks/data/timeline";
import { mockDb } from "@/mocks/db";

import { MOCK_CREATOR, leadEventsOf, recordLeadEvent } from "./lead-events";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse, mockWorkbook } from "./shared";

/**
 * LEAD-001 … LEAD-004 · The backend's lead endpoints (backend/docs/api/leads.md), as far as
 * the frontend uses them: search rules, the default stage filter, cursor paging, the capped
 * total, the stats, idempotent create, and duplicates that are flagged rather than refused.
 * LEAD-008 · Assignees (by the previewed role's scope) and assignment.
 * LEAD-005…007 · The timeline (derived from each lead once, plus what is written here),
 * notes, stage changes and reopening, with the backend's stage rules, Idempotency-Key replay
 * and 409s.
 */

/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;
const DEFAULT_LIMIT = 50;
/** GET /leads/{id}/timeline returns 100 events unless asked for fewer. */
const TIMELINE_DEFAULT_LIMIT = 100;
const MAX_LIMIT = 100;

function isStage(value: string): value is LeadStage {
  return LEAD_STAGES.some((stage) => stage === value);
}

function isLeadAreaLevel(value: string): value is LeadAreaLevel {
  return LEAD_AREA_LEVELS.some((level) => level === value);
}

/** q matches the name (contains), the mobile's digits (contains) and the inquiry number (exact). */
function matchesSearch(lead: LeadWire, q: string): boolean {
  const query = q.trim().toLowerCase();
  if (query === "") {
    return true;
  }
  const digits = query.replace(/\D/g, "");
  return (
    lead.farmer_name.toLowerCase().includes(query) ||
    lead.inquiry_no.toLowerCase() === query ||
    (digits !== "" && lead.mobile.includes(digits))
  );
}

/**
 * The order `GET /leads` lists in, as the backend sorts (BE-001): names ignore case, a lead
 * without a value comes last in both orders, and ties break by id so pages never repeat a row.
 */
function sortLeads(leads: readonly LeadWire[], sort: string, direction: 1 | -1): LeadWire[] {
  const byKey = (a: LeadWire, b: LeadWire): number => {
    switch (sort) {
      case "farmer_name":
        return a.farmer_name.toLowerCase().localeCompare(b.farmer_name.toLowerCase(), "en-IN");
      case "estimated_value":
        return Number(a.estimated_value) - Number(b.estimated_value);
      default:
        return Date.parse(a.created_at) - Date.parse(b.created_at);
    }
  };
  return [...leads].sort((a, b) => {
    if (
      sort === "estimated_value" &&
      (a.estimated_value === null) !== (b.estimated_value === null)
    ) {
      return a.estimated_value === null ? 1 : -1;
    }
    return (byKey(a, b) || a.id.localeCompare(b.id)) * direction;
  });
}

/** The list omits duplicate links; only the detail endpoint carries them. */
function toListRow(lead: LeadWire): LeadWire {
  return { ...lead, duplicates: [] };
}

/**
 * The filters GET /leads and GET /leads/stats share, so a count and its list always agree.
 * No stage filter means every stage except merged, as on the backend.
 */
function filterLeads(params: URLSearchParams): LeadWire[] {
  const stages = (params.get("stage") ?? "")
    .split(",")
    .map((stage) => stage.trim())
    .filter(isStage);
  const source = params.get("source");
  const inquiryType = params.get("inquiry_type");
  const q = params.get("q") ?? "";
  const areas = new Set(
    (params.get("territory_id") ?? "")
      .split(",")
      .map((id) => id.trim())
      .filter((id) => id !== ""),
  );

  return mockDb.leads.filter((lead) => {
    if (stages.length > 0 ? !stages.includes(lead.stage) : lead.stage === "merged") {
      return false;
    }
    if (source !== null && source !== "" && lead.source !== source) return false;
    if (inquiryType !== null && inquiryType !== "" && lead.inquiry_type !== inquiryType) {
      return false;
    }
    if (areas.size > 0 && !inAnyArea(lead, areas)) return false;
    return matchesSearch(lead, q);
  });
}

/** A lead sits in an area when its own territory, or any territory above it, is one of them. */
function inAnyArea(lead: LeadWire, areas: ReadonlySet<string>): boolean {
  return mockTerritoryLineage(lead.territory.id).some((territory) => areas.has(territory.id));
}

/**
 * GET /leads/areas — the areas at one level (under a parent, if given) that hold at least one
 * lead the caller can see, with how many. Merged leads don't count, as on the list.
 */
function leadAreasOf(level: LeadAreaLevel, parentId: string | null): LeadAreaWire[] {
  const counts = new Map<string, number>();
  for (const lead of mockDb.leads) {
    if (lead.stage === "merged") continue;
    const area = mockTerritoryLineage(lead.territory.id).find((item) => item.level === level);
    if (area === undefined) continue;
    if (parentId !== null && area.parent?.id !== parentId) continue;
    counts.set(area.id, (counts.get(area.id) ?? 0) + 1);
  }
  return MOCK_TERRITORIES.filter((territory) => counts.has(territory.id))
    .map((territory) => ({
      id: territory.id,
      name: territory.name,
      level,
      code: territory.code,
      parent: territory.parent,
      lead_count: counts.get(territory.id) ?? 0,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Every stage and priority is present, 0 when empty — as the backend promises. */
function statsOf(leads: readonly LeadWire[]): LeadStatsWire {
  const byStage = Object.fromEntries(LEAD_STAGES.map((stage) => [stage, 0]));
  const byPriority: LeadStatsWire["by_priority"] = { hot: 0, warm: 0, cold: 0 };
  let unassigned = 0;
  for (const lead of leads) {
    byStage[lead.stage] = (byStage[lead.stage] ?? 0) + 1;
    if (lead.priority !== null) {
      byPriority[lead.priority] += 1;
    }
    if (lead.owner === null) {
      unassigned += 1;
    }
  }
  return { total: leads.length, by_stage: byStage, by_priority: byPriority, unassigned };
}

function nextInquiryNumber(): string {
  const highest = Math.max(
    122,
    ...mockDb.leads.map((lead) => Number(lead.inquiry_no.split("/").at(-1) ?? "0")),
  );
  return `POL/GJ/2026-27/${String(highest + 1).padStart(5, "0")}`;
}

function createLeadFrom(body: CreateLeadRequest): LeadWire | Response {
  const territory = findMockTerritory(body.territory_id);
  if (territory === undefined) {
    return errorResponse(422, "validation_error", "Some fields need correcting.", {
      territory_id: "no such territory",
    });
  }
  if (territory.level === "state") {
    return errorResponse(422, "validation_error", "Some fields need correcting.", {
      territory_id: "a lead sits in a district, taluka or village, not a state",
    });
  }
  const office = mockOfficeFor(territory);
  if (office === null) {
    return errorResponse(
      422,
      "territory_without_org_unit",
      "No sales org unit covers this territory, and no fallback unit is configured.",
      { territory_id: "no org unit covers this territory" },
    );
  }

  const activeCrops = mockLookupRows("crops").filter((crop) => crop.is_active !== false);
  const unknownCrop = body.crops.findIndex(
    (code) => !activeCrops.some((crop) => crop.code === code),
  );
  if (unknownCrop !== -1) {
    return errorResponse(422, "validation_error", "Some fields need correcting.", {
      [`crops.${String(unknownCrop)}`]: "not an active crop",
    });
  }

  const now = new Date().toISOString();
  const id = mockUuid(MOCK_ID_SPACE.lead, 100_000 + mockDb.leads.length + 1);
  const inquiryNo = nextInquiryNumber();
  const matches = mockDb.leads.filter(
    (lead) => lead.mobile === body.mobile || (body.email !== null && lead.email === body.email),
  );

  const lead: LeadWire = {
    id,
    inquiry_no: inquiryNo,
    stage: "new",
    inquiry_type: body.inquiry_type,
    mis_system: body.mis_system,
    source: body.source ?? "employee",
    farmer_name: body.farmer_name,
    mobile: body.mobile,
    email: body.email,
    territory: toTerritoryRef(territory),
    village: body.village,
    owner: MOCK_CREATOR ?? null,
    owner_org_unit: office,
    assigned_partner: null,
    score: null,
    priority: null,
    estimated_value: body.estimated_value === null ? null : Number(body.estimated_value).toFixed(2),
    crops: body.crops.map((code) => ({
      code,
      name: activeCrops.find((crop) => crop.code === code)?.name ?? code,
      is_active: true,
    })),
    land_acres: body.land_acres === null ? null : Number(body.land_acres).toFixed(2),
    lost_reason: null,
    lost_note: null,
    reopen_count: 0,
    merged_into: null,
    first_contacted_at: null,
    last_activity_at: now,
    created_at: now,
    created_by: MOCK_CREATOR ?? null,
    duplicates: matches.map((match, index) => ({
      link_id: mockUuid(MOCK_ID_SPACE.duplicate, 100_000 + mockDb.leads.length + index),
      lead_id: match.id,
      inquiry_no: match.inquiry_no,
      signal: match.mobile === body.mobile ? "mobile" : "email",
      score: "1.00",
      state: "pending",
    })),
  };

  // Rule 6: duplicates are flagged on both leads, never refused.
  for (const [index, match] of matches.entries()) {
    match.duplicates = [
      ...(match.duplicates ?? []),
      {
        link_id: mockUuid(MOCK_ID_SPACE.duplicate, 100_000 + mockDb.leads.length + index),
        lead_id: id,
        inquiry_no: inquiryNo,
        signal: match.mobile === body.mobile ? "mobile" : "email",
        score: "1.00",
        state: "pending",
      },
    ];
  }

  return lead;
}

/** The backend's stage machine (backend/api/domain/leads.py). */
const MOCK_TRANSITIONS: Readonly<Partial<Record<LeadStage, readonly LeadStage[]>>> = {
  new: ["contacted", "lost"],
  contacted: ["qualified", "lost"],
  qualified: ["quoted", "lost"],
  quoted: ["negotiation", "won", "lost"],
  negotiation: ["won", "lost"],
};
const TERMINAL_STAGES: readonly LeadStage[] = ["won", "lost", "merged"];

/**
 * TODO(QUOT-001): the mock has no quotations yet. It treats a lead in negotiation as having
 * an accepted quotation, so both answers to "Mark as won" can be previewed: a quoted lead
 * is refused with quotation_required, a lead in negotiation is won.
 */
function hasAcceptedQuotation(lead: LeadWire): boolean {
  return lead.stage === "negotiation";
}

/** Idempotency-Key handling shared by the stage endpoints: 400, replay or 409. */
function replayStageChange(
  request: Request,
  leadId: string,
  body: unknown,
): { kind: "fresh"; key: string; serialized: string } | { kind: "respond"; response: Response } {
  const key = request.headers.get("idempotency-key")?.trim() ?? "";
  if (key === "") {
    return {
      kind: "respond",
      response: errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required on this request.",
      ),
    };
  }
  const serialized = JSON.stringify({ path: new URL(request.url).pathname, leadId, body });
  const replay = mockDb.stageChanges.get(key);
  if (replay === undefined) {
    return { kind: "fresh", key, serialized };
  }
  if (replay.body !== serialized) {
    return {
      kind: "respond",
      response: errorResponse(
        409,
        "idempotency_key_reused",
        "This Idempotency-Key was already used for a different request.",
      ),
    };
  }
  const lead = mockDb.leads.find((item) => item.id === replay.leadId);
  return {
    kind: "respond",
    response: lead
      ? HttpResponse.json({ data: lead } satisfies LeadResponseWire)
      : errorResponse(404, "not_found", "No such lead."),
  };
}

const patchLeadRequestSchema = createLeadRequestSchema.omit({ note: true }).partial();

function validationError(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function mayDo(action: "edit" | "delete"): boolean {
  return mockPermissionsFor(readMockRole()).some(
    (permission) => permission.module === "leads" && permission.actions.includes(action),
  );
}

/** Every pending pair once, both leads still there, newest lead first (LEAD-012). */
function pendingPairs(): DuplicatePairWire[] {
  const seen = new Set<string>();
  const pairs: DuplicatePairWire[] = [];
  for (const lead of mockDb.leads) {
    for (const link of lead.duplicates ?? []) {
      if (link.state !== "pending" || seen.has(link.link_id)) continue;
      const other = mockDb.leads.find((item) => item.id === link.lead_id);
      // A merged lead's pairs were re-pointed or closed when it merged.
      if (other === undefined || other.stage === "merged" || lead.stage === "merged") continue;
      seen.add(link.link_id);
      const [a, b] = lead.created_at >= other.created_at ? [lead, other] : [other, lead];
      pairs.push({
        link_id: link.link_id,
        signal: link.signal,
        score: link.score ?? null,
        state: "pending",
        created_at: a.created_at,
        lead_a: a,
        lead_b: b,
      });
    }
  }
  return pairs.sort((x, y) => y.created_at.localeCompare(x.created_at));
}

/** Sets one pair's state on both leads. */
function settleLink(linkId: string, state: "merged" | "dismissed"): void {
  for (const lead of mockDb.leads) {
    lead.duplicates = (lead.duplicates ?? []).map((link) =>
      link.link_id === linkId ? { ...link, state } : link,
    );
  }
}

/**
 * Who the previewed role may make an owner: everyone for a global or office-tree lead
 * scope, nobody otherwise — as the backend's GET /leads/assignees answers.
 */
function mockAssignees(): AssigneeListWire["data"] {
  const scope = mockPermissionsFor(readMockRole()).find((grant) => grant.module === "leads")?.scope;
  if (scope !== "global" && scope !== "org_subtree") {
    return [];
  }
  return MOCK_STAFF.map((person) => ({
    id: person.id,
    full_name: person.full_name,
    org_unit: null,
  }));
}

export const leadHandlers = [
  http.get(buildApiUrl("/leads"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }

    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 42, farmer_name: null }], meta: { limit: "25" } });
    }

    const sort = url.searchParams.get("sort") ?? "created_at";
    const direction = url.searchParams.get("order") === "asc" ? 1 : -1;

    const matches = scenario === "empty" ? [] : filterLeads(url.searchParams);

    const sorted = sortLeads(matches, sort, direction);
    const page = sorted.slice(offset, offset + limit);
    const hasMore = offset + limit < sorted.length;
    const counted = url.searchParams.get("include_total") === "true";

    const body: LeadPageWire = {
      data: page.map(toListRow),
      meta: {
        limit,
        next_cursor: hasMore ? encodeCursor(offset + limit) : null,
        total: counted ? Math.min(sorted.length, TOTAL_CEILING) : null,
        total_capped: counted && sorted.length > TOTAL_CEILING,
      },
    };
    return HttpResponse.json(body);
  }),

  // Before /leads/:leadId, as on the backend, so "stats" is never read as a lead ID.
  http.get(buildApiUrl("/leads/stats"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ total: "12", by_stage: null });
    }

    const matches = scenario === "empty" ? [] : filterLeads(new URL(request.url).searchParams);
    return HttpResponse.json(statsOf(matches));
  }),

  // Before /leads/:leadId, as on the backend, so "areas" is never read as a lead ID.
  http.get(buildApiUrl("/leads/areas"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const level = url.searchParams.get("level") ?? "";
    if (!isLeadAreaLevel(level)) {
      return errorResponse(422, "validation_error", "Choose a level: state, district or taluka.", {
        level: "must be state, district or taluka",
      });
    }
    const parentId = url.searchParams.get("parent_id");
    const data = scenario === "empty" ? [] : leadAreasOf(level, parentId === "" ? null : parentId);
    return HttpResponse.json({ data });
  }),

  // Before /leads/:leadId, as on the backend, so "assignees" is never read as a lead ID.
  http.get(buildApiUrl("/leads/assignees"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const body: AssigneeListWire = { data: mockAssignees() };
    return HttpResponse.json(body);
  }),

  /** LEAD-009 · The list as a file. Before /leads/:leadId. */
  http.get(buildApiUrl("/leads/export"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return mockWorkbook(
      "leads",
      ["Inquiry", "Farmer", "Mobile", "Stage", "Territory"],
      mockDb.leads.map((lead) => [
        lead.inquiry_no,
        lead.farmer_name,
        lead.mobile,
        lead.stage,
        lead.territory.name,
      ]),
    );
  }),

  /** LEAD-012 · The duplicate review queue. Before /leads/:leadId. */
  http.get(buildApiUrl("/leads/duplicates"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const url = new URL(request.url);
    const limit = Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") ?? 20) || 20);
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : decodeCursor(cursor);
    if (offset === null) return validationError({ cursor: "malformed cursor" });
    const pairs = scenario === "empty" ? [] : pendingPairs();
    const body: DuplicatePageWire = {
      data: pairs.slice(offset, offset + limit),
      meta: {
        limit,
        next_cursor: offset + limit < pairs.length ? encodeCursor(offset + limit) : null,
        total: null,
        total_capped: false,
      },
    };
    return HttpResponse.json(body);
  }),

  /** LEAD-012 · Not a duplicate: the pair leaves the queue; both timelines record it. */
  http.post(buildApiUrl("/leads/duplicates/:linkId/dismiss"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const linkId = String(params.linkId);
    const idempotency = replayStageChange(request, linkId, null);
    if (idempotency.kind === "respond") return idempotency.response;
    if (!mayDo("edit")) return errorResponse(403, "forbidden", "You may not review duplicates.");
    const pair = pendingPairs().find((item) => item.link_id === linkId);
    if (pair === undefined) return errorResponse(404, "not_found", "No such pending pair.");
    settleLink(linkId, "dismissed");
    for (const id of [pair.lead_a.id, pair.lead_b.id]) {
      const lead = mockDb.leads.find((item) => item.id === id);
      if (lead !== undefined)
        recordLeadEvent(lead, "lead.duplicate_dismissed", { link_id: linkId });
    }
    mockDb.stageChanges.set(idempotency.key, {
      body: idempotency.serialized,
      leadId: pair.lead_a.id,
    });
    return HttpResponse.json({ data: { link_id: linkId, state: "dismissed" } });
  }),

  http.get(buildApiUrl("/leads/:leadId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const lead = mockDb.leads.find((item) => item.id === params.leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    const body: LeadResponseWire = { data: lead };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/leads/:leadId/timeline"), async ({ params, request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const lead = mockDb.leads.find((item) => item.id === params.leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 7, kind: null }], meta: { limit: "20" } });
    }

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(
        1,
        Number(url.searchParams.get("limit") ?? TIMELINE_DEFAULT_LIMIT) || TIMELINE_DEFAULT_LIMIT,
      ),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }

    const events = scenario === "empty" ? [] : [...leadEventsOf(lead)].sort(newestFirst);
    const hasMore = offset + limit < events.length;
    const body: TimelinePageWire = {
      data: events.slice(offset, offset + limit),
      meta: { limit, next_cursor: hasMore ? encodeCursor(offset + limit) : null },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/leads/:leadId/notes"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required on this request.",
      );
    }

    const lead = mockDb.leads.find((item) => item.id === params.leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }

    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ leadId: lead.id, body: raw });
    const replay = mockDb.noteCreations.get(key);
    if (replay !== undefined) {
      if (replay.body !== serialized) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "This Idempotency-Key was already used for a different request.",
        );
      }
      return HttpResponse.json({ data: replay.event }, { status: 201 });
    }

    const parsed = addLeadNoteRequestSchema.safeParse(raw);
    if (!parsed.success) {
      const fields = Object.fromEntries(
        summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
      );
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }

    const event = recordLeadEvent(lead, "lead.note_added", { note: parsed.data.note });
    mockDb.noteCreations.set(key, { body: serialized, event });
    return HttpResponse.json({ data: event }, { status: 201 });
  }),

  http.post(buildApiUrl("/leads/:leadId/transition"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const leadId = String(params.leadId);
    const idempotency = replayStageChange(request, leadId, raw);
    if (idempotency.kind === "respond") return idempotency.response;

    const lead = mockDb.leads.find((item) => item.id === leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    const parsed = transitionLeadRequestSchema.safeParse(raw);
    if (!parsed.success) {
      const fields = Object.fromEntries(
        summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
      );
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const body = parsed.data;
    const current = lead.stage;

    if (body.expected_stage !== current) {
      return errorResponse(
        409,
        "stage_changed",
        "The lead has moved to a different stage since you loaded it.",
        { stage: current },
      );
    }
    if (TERMINAL_STAGES.includes(current)) {
      return errorResponse(422, "stage_terminal", "This lead is closed and cannot change stage.", {
        stage: current,
      });
    }
    if (!(MOCK_TRANSITIONS[current] ?? []).includes(body.to_stage)) {
      return errorResponse(
        422,
        "invalid_transition",
        `A ${current} lead cannot move to ${body.to_stage}.`,
        {
          to_stage: body.to_stage,
        },
      );
    }
    if (body.to_stage === "quoted" || body.to_stage === "negotiation") {
      return errorResponse(
        422,
        "quotation_required",
        "This stage is reached by sending a quotation, not from here.",
        {
          to_stage: body.to_stage,
        },
      );
    }
    if (body.to_stage === "won" && !hasAcceptedQuotation(lead)) {
      return errorResponse(
        422,
        "quotation_required",
        "This stage needs an accepted quotation on the lead.",
        {
          to_stage: body.to_stage,
        },
      );
    }

    const payload: Record<string, unknown> = { from: current, to: body.to_stage };
    if (body.to_stage === "lost") {
      const reason = mockLookupRows("lost-reasons").find(
        (row) => row.id === body.lost_reason_id && row.is_active,
      );
      if (reason === undefined) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          lost_reason_id: body.lost_reason_id
            ? "not an active lost reason"
            : "a lost reason is required",
        });
      }
      payload.lost_reason_id = reason.id;
      payload.lost_note = body.lost_note;
      lead.lost_reason = { id: reason.id, code: reason.code, name: reason.name };
      lead.lost_note = body.lost_note;
      mockDb.lostFrom.set(lead.id, current);
    }

    recordLeadEvent(lead, "lead.stage_changed", payload);
    lead.stage = body.to_stage;
    if (body.to_stage === "contacted" && lead.first_contacted_at === null) {
      lead.first_contacted_at = lead.last_activity_at;
    }
    mockDb.stageChanges.set(idempotency.key, { body: idempotency.serialized, leadId: lead.id });
    return HttpResponse.json({ data: lead } satisfies LeadResponseWire);
  }),

  http.post(buildApiUrl("/leads/:leadId/reopen"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const leadId = String(params.leadId);
    const idempotency = replayStageChange(request, leadId, raw);
    if (idempotency.kind === "respond") return idempotency.response;

    const lead = mockDb.leads.find((item) => item.id === leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    const parsed = reopenLeadRequestSchema.safeParse(raw);
    if (!parsed.success) {
      const fields = Object.fromEntries(
        summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
      );
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    if (lead.stage !== "lost") {
      return errorResponse(422, "stage_terminal", "Only a lost lead can be reopened.", {
        stage: lead.stage,
      });
    }

    const lostEvent = leadEventsOf(lead).find(
      (event) => event.kind === "lead.stage_changed" && event.payload?.to === "lost",
    );
    const seededFrom = LEAD_STAGES.find((stage) => stage === lostEvent?.payload?.from);
    const target = mockDb.lostFrom.get(lead.id) ?? seededFrom ?? "new";
    recordLeadEvent(lead, "lead.reopened", {
      from: "lost",
      to: target,
      lost_reason_id: lead.lost_reason?.id ?? null,
      lost_note: lead.lost_note,
      note: parsed.data.note,
    });
    lead.stage = target;
    lead.lost_reason = null;
    lead.lost_note = null;
    lead.reopen_count += 1;
    mockDb.lostFrom.delete(lead.id);
    mockDb.stageChanges.set(idempotency.key, { body: idempotency.serialized, leadId: lead.id });
    return HttpResponse.json({ data: lead } satisfies LeadResponseWire);
  }),

  http.post(buildApiUrl("/leads/:leadId/assign"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const leadId = String(params.leadId);
    const idempotency = replayStageChange(request, leadId, raw);
    if (idempotency.kind === "respond") return idempotency.response;

    const parsed = assignLeadRequestSchema.safeParse(raw);
    if (!parsed.success) {
      const fields = Object.fromEntries(
        summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
      );
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const body = parsed.data;
    const owner =
      body.owner_user_id === undefined || body.owner_user_id === null
        ? null
        : mockAssignees().find((person) => person.id === body.owner_user_id);
    if (owner === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        owner_user_id: "not assignable by you",
      });
    }

    const lead = mockDb.leads.find((item) => item.id === leadId);
    if (!lead) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    if (TERMINAL_STAGES.includes(lead.stage)) {
      return errorResponse(422, "stage_terminal", "This lead is closed and cannot be reassigned.", {
        stage: lead.stage,
      });
    }

    // Each id travels with its name, as the backend writes them (BE-006).
    const payload: Record<string, unknown> = {};
    if (body.owner_user_id !== undefined) {
      if (lead.owner !== null && lead.owner.id !== owner?.id) {
        payload.previous_owner_user_id = lead.owner.id;
        payload.previous_owner_name = lead.owner.full_name;
      }
      lead.owner = owner === null ? null : { id: owner.id, full_name: owner.full_name };
      payload.owner_user_id = body.owner_user_id;
      payload.owner_name = owner?.full_name ?? null;
    }
    if (body.assigned_partner_id !== undefined) {
      const partner =
        body.assigned_partner_id === null
          ? null
          : MOCK_PARTNERS.find((item) => item.id === body.assigned_partner_id);
      if (partner === undefined) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          assigned_partner_id: "not in your scope",
        });
      }
      lead.assigned_partner =
        partner === null
          ? null
          : { id: partner.id, name: partner.name, partner_type: partner.partner_type };
      payload.assigned_partner_id = body.assigned_partner_id;
      payload.partner_name = partner?.name ?? null;
    }

    recordLeadEvent(lead, "lead.assigned", payload);
    mockDb.stageChanges.set(idempotency.key, { body: idempotency.serialized, leadId: lead.id });
    return HttpResponse.json({ data: lead } satisfies LeadResponseWire);
  }),

  /** LEAD-010 · Correct the lead's own fields; a closed lead is refused. */
  http.patch(buildApiUrl("/leads/:leadId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const leadId = String(params.leadId);
    const idempotency = replayStageChange(request, leadId, raw);
    if (idempotency.kind === "respond") return idempotency.response;
    if (!mayDo("edit")) return errorResponse(403, "forbidden", "You may not edit leads.");
    const parsed = patchLeadRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return validationError(
        Object.fromEntries(
          summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
        ),
      );
    }
    const lead = mockDb.leads.find((item) => item.id === leadId);
    if (!lead) return errorResponse(404, "not_found", "No such lead.");
    if (TERMINAL_STAGES.includes(lead.stage)) {
      return errorResponse(422, "stage_terminal", "This lead is closed and cannot be edited.", {
        stage: lead.stage,
      });
    }
    const body = parsed.data;
    const changed: Record<string, unknown> = {};
    if (body.territory_id !== undefined && body.territory_id !== lead.territory.id) {
      const territory = findMockTerritory(body.territory_id);
      if (territory === undefined || territory.level === "state") {
        return validationError({ territory_id: "a district, taluka or village in your scope" });
      }
      lead.territory = toTerritoryRef(territory);
      changed.territory_id = body.territory_id;
    }
    if (body.crops !== undefined) {
      const crops = mockLookupRows("crops");
      lead.crops = body.crops.map((code) => ({
        code,
        name: crops.find((crop) => crop.code === code)?.name ?? code,
        is_active: crops.find((crop) => crop.code === code)?.is_active !== false,
      }));
      changed.crops = body.crops;
    }
    const scalar = {
      farmer_name: body.farmer_name,
      mobile: body.mobile,
      email: body.email,
      village: body.village,
      inquiry_type: body.inquiry_type,
      mis_system: body.mis_system,
      source: body.source ?? undefined,
      estimated_value:
        body.estimated_value === undefined
          ? undefined
          : body.estimated_value === null
            ? null
            : Number(body.estimated_value).toFixed(2),
      land_acres:
        body.land_acres === undefined
          ? undefined
          : body.land_acres === null
            ? null
            : Number(body.land_acres).toFixed(2),
    } as const;
    for (const [key, value] of Object.entries(scalar)) {
      if (value === undefined) continue;
      Object.assign(lead, { [key]: value });
      changed[key] = value;
    }
    if (Object.keys(changed).length > 0) recordLeadEvent(lead, "lead.updated", { changed });
    mockDb.stageChanges.set(idempotency.key, { body: idempotency.serialized, leadId: lead.id });
    return HttpResponse.json({ data: lead } satisfies LeadResponseWire);
  }),

  /** LEAD-011 · Soft delete (leads.delete). The mock drops it; its pending pairs close. */
  http.delete(buildApiUrl("/leads/:leadId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const leadId = String(params.leadId);
    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(400, "idempotency_key_required", "An Idempotency-Key is required.");
    }
    if (!mayDo("delete")) return errorResponse(403, "forbidden", "You may not delete leads.");
    const lead = mockDb.leads.find((item) => item.id === leadId);
    if (lead !== undefined) {
      for (const link of lead.duplicates ?? []) {
        if (link.state === "pending") settleLink(link.link_id, "dismissed");
      }
      mockDb.leads = mockDb.leads.filter((item) => item.id !== leadId);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  /** LEAD-012 · Merge this lead (the loser) into the survivor. */
  http.post(buildApiUrl("/leads/:leadId/merge"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const leadId = String(params.leadId);
    const idempotency = replayStageChange(request, leadId, raw);
    if (idempotency.kind === "respond") return idempotency.response;
    if (!mayDo("edit")) return errorResponse(403, "forbidden", "You may not merge leads.");
    const into =
      typeof raw === "object" && raw !== null && "into_lead_id" in raw ? raw.into_lead_id : null;
    if (typeof into !== "string" || into === "") {
      return validationError({ into_lead_id: "required" });
    }
    if (into === leadId) {
      return errorResponse(422, "merge_self", "A lead cannot merge into itself.");
    }
    const loser = mockDb.leads.find((item) => item.id === leadId);
    const survivor = mockDb.leads.find((item) => item.id === into);
    if (!loser || !survivor) return errorResponse(404, "not_found", "No such lead.");
    if (TERMINAL_STAGES.includes(loser.stage) || TERMINAL_STAGES.includes(survivor.stage)) {
      return errorResponse(422, "merge_terminal", "A won, lost or merged lead cannot be merged.");
    }
    for (const link of loser.duplicates ?? []) {
      if (link.state !== "pending") continue;
      settleLink(link.link_id, link.lead_id === survivor.id ? "merged" : "dismissed");
    }
    loser.stage = "merged";
    loser.merged_into = { id: survivor.id, inquiry_no: survivor.inquiry_no };
    const payload = { loser: loser.id, survivor: survivor.id };
    recordLeadEvent(survivor, "lead.merged", payload);
    recordLeadEvent(loser, "lead.merged", payload);
    mockDb.stageChanges.set(idempotency.key, {
      body: idempotency.serialized,
      leadId: survivor.id,
    });
    return HttpResponse.json({ data: survivor } satisfies LeadResponseWire);
  }),

  http.post(buildApiUrl("/leads"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required on this request.",
      );
    }

    const raw: unknown = await request.json();
    const serialized = JSON.stringify(raw);
    const replay = mockDb.leadCreations.get(key);
    if (replay !== undefined) {
      if (replay.body !== serialized) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "This Idempotency-Key was already used for a different request.",
        );
      }
      const lead = mockDb.leads.find((item) => item.id === replay.leadId);
      if (lead !== undefined) {
        const body: LeadResponseWire = { data: lead };
        return HttpResponse.json(body, { status: 201 });
      }
    }

    const parsed = createLeadRequestSchema.safeParse(raw);
    if (!parsed.success) {
      const fields = Object.fromEntries(
        summarizeSchemaIssues(parsed.error).map((issue) => [issue.path, issue.message]),
      );
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }

    const created = createLeadFrom(parsed.data);
    if (created instanceof Response) {
      return created;
    }
    mockDb.leads = [created, ...mockDb.leads];
    mockDb.leadCreations.set(key, { body: serialized, leadId: created.id });

    const body: LeadResponseWire = { data: created };
    return HttpResponse.json(body, { status: 201 });
  }),
];
