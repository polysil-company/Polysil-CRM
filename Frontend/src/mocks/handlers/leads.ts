import { http, HttpResponse } from "msw";

import {
  createLeadRequestSchema,
  LEAD_STAGES,
  type CreateLeadRequest,
  type LeadPageWire,
  type LeadResponseWire,
  type LeadStage,
  type LeadWire,
} from "@/features/leads/api/leads.schemas";
import { summarizeSchemaIssues } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import { findMockTerritory, mockOfficeFor, toTerritoryRef } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

/**
 * LEAD-001 … LEAD-004 · The backend's lead endpoints (backend/docs/api/leads.md), as far as
 * the frontend uses them: search rules, the default stage filter, cursor paging, the capped
 * total, idempotent create, and duplicates that are flagged rather than refused.
 */

/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 100;

/** The signed-in staff user in the mock (usr-001 in the session mock owns what they create). */
const MOCK_CREATOR = MOCK_STAFF[0];

function errorResponse(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
): Response {
  return HttpResponse.json(
    { error: { code, message, ...(fields === undefined ? {} : { fields }) } },
    { status },
  );
}

function isStage(value: string): value is LeadStage {
  return LEAD_STAGES.some((stage) => stage === value);
}

/** The mock's cursor is an offset, base64url-encoded like the backend's opaque cursors. */
function encodeCursor(offset: number): string {
  return btoa(`offset:${String(offset)}`)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function decodeCursor(cursor: string): number | null {
  try {
    const match = /^offset:(\d+)$/.exec(atob(cursor.replace(/-/g, "+").replace(/_/g, "/")));
    return match?.[1] === undefined ? null : Number(match[1]);
  } catch {
    return null;
  }
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
 * TODO(LEAD-001): the real backend does not sort yet — it always lists newest first. The mock
 * honours the `sort` and `order` we asked for, so the UI can be previewed as intended.
 */
function compareLeads(a: LeadWire, b: LeadWire, sort: string): number {
  switch (sort) {
    case "farmer_name":
      return a.farmer_name.localeCompare(b.farmer_name, "en-IN");
    case "estimated_value":
      return Number(a.estimated_value ?? -1) - Number(b.estimated_value ?? -1);
    default:
      return Date.parse(a.created_at) - Date.parse(b.created_at) || a.id.localeCompare(b.id);
  }
}

/** The list omits duplicate links; only the detail endpoint carries them. */
function toListRow(lead: LeadWire): LeadWire {
  return { ...lead, duplicates: [] };
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
  const office = mockOfficeFor(territory);
  if (office === null) {
    return errorResponse(
      422,
      "territory_without_org_unit",
      "No sales org unit covers this territory, and no fallback unit is configured.",
      { territory_id: "no org unit covers this territory" },
    );
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

    const stages = (url.searchParams.get("stage") ?? "")
      .split(",")
      .map((stage) => stage.trim())
      .filter(isStage);
    const source = url.searchParams.get("source");
    const inquiryType = url.searchParams.get("inquiry_type");
    const q = url.searchParams.get("q") ?? "";
    const sort = url.searchParams.get("sort") ?? "created_at";
    const direction = url.searchParams.get("order") === "asc" ? 1 : -1;

    const matches =
      scenario === "empty"
        ? []
        : mockDb.leads.filter((lead) => {
            if (stages.length > 0 ? !stages.includes(lead.stage) : lead.stage === "merged") {
              return false;
            }
            if (source !== null && source !== "" && lead.source !== source) return false;
            if (inquiryType !== null && inquiryType !== "" && lead.inquiry_type !== inquiryType) {
              return false;
            }
            return matchesSearch(lead, q);
          });

    const sorted = [...matches].sort((a, b) => compareLeads(a, b, sort) * direction);
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
