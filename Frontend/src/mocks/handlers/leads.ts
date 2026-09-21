import { http, HttpResponse } from "msw";

import {
  createLeadRequestSchema,
  LEAD_SORT_FIELDS,
  LEAD_SOURCES,
  LEAD_STATUSES,
  ORDER_TYPES,
  type Lead,
  type LeadSortField,
  type LeadSummary,
} from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

function isOneOf<T extends string>(values: readonly T[], value: string): value is T {
  return values.some((item) => item === value);
}

function positiveInt(raw: string | null, fallback: number): number {
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function compareLeads(a: Lead, b: Lead, field: LeadSortField): number {
  switch (field) {
    case "customerName":
      return a.customerName.localeCompare(b.customerName, "en-IN");
    case "estimatedValue":
      return (a.estimatedValue ?? -1) - (b.estimatedValue ?? -1);
    case "winProbability":
      return a.winProbability - b.winProbability;
    case "followUpAt":
      return (
        (a.followUpAt ? Date.parse(a.followUpAt) : Infinity) -
        (b.followUpAt ? Date.parse(b.followUpAt) : Infinity)
      );
    case "createdAt":
      return Date.parse(a.createdAt) - Date.parse(b.createdAt);
  }
}

function countBy<T extends string>(
  keys: readonly T[],
  leads: readonly Lead[],
  read: (lead: Lead) => T,
): Record<T, number> {
  const counts = Object.fromEntries(keys.map((key) => [key, 0])) as Record<T, number>; // eslint-disable-line @typescript-eslint/consistent-type-assertions -- Object.fromEntries cannot express exhaustive keys; every key is initialised on this line.
  for (const lead of leads) {
    counts[read(lead)] += 1;
  }
  return counts;
}

function isToday(iso: string | null, now: Date): boolean {
  if (!iso) return false;
  const date = new Date(iso);
  return date.toDateString() === now.toDateString();
}

export const leadHandlers = [
  // Registered before /leads/:leadId so "summary" is never read as an id.
  http.get(buildApiUrl("/leads/summary"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const leads = scenario === "empty" ? [] : mockDb.leads;
    const now = new Date();
    const summary: LeadSummary = {
      total: leads.length,
      byStatus: countBy(LEAD_STATUSES, leads, (lead) => lead.status),
      bySource: countBy(LEAD_SOURCES, leads, (lead) => lead.source),
      byType: countBy(ORDER_TYPES, leads, (lead) => lead.type),
      followUpsDueToday: leads.filter((lead) => isToday(lead.followUpAt, now)).length,
    };
    return HttpResponse.json(summary);
  }),

  http.get(buildApiUrl("/leads"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const page = positiveInt(url.searchParams.get("page"), 1);
    const pageSize = Math.min(100, positiveInt(url.searchParams.get("pageSize"), 25));
    const sortParam = url.searchParams.get("sort") ?? "";
    const sort: LeadSortField = isOneOf(LEAD_SORT_FIELDS, sortParam) ? sortParam : "createdAt";
    const direction = url.searchParams.get("order") === "asc" ? 1 : -1;
    const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const statuses = url.searchParams
      .getAll("status")
      .filter((value) => isOneOf(LEAD_STATUSES, value));
    const sources = url.searchParams
      .getAll("source")
      .filter((value) => isOneOf(LEAD_SOURCES, value));
    const types = url.searchParams.getAll("type").filter((value) => isOneOf(ORDER_TYPES, value));

    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({
        items: [{ id: 42, customerName: null }],
        page: "1",
        total: "many",
      });
    }

    const matches =
      scenario === "empty"
        ? []
        : mockDb.leads.filter((lead) => {
            if (statuses.length > 0 && !statuses.includes(lead.status)) return false;
            if (sources.length > 0 && !sources.includes(lead.source)) return false;
            if (types.length > 0 && !types.includes(lead.type)) return false;
            if (query === "") return true;
            return [
              lead.customerName,
              lead.phone,
              lead.code,
              lead.district,
              lead.village ?? "",
            ].some((field) => field.toLowerCase().includes(query));
          });

    const sorted = [...matches].sort((a, b) => compareLeads(a, b, sort) * direction);
    const start = (page - 1) * pageSize;

    return HttpResponse.json({
      items: sorted.slice(start, start + pageSize),
      page,
      pageSize,
      total: sorted.length,
    });
  }),

  http.get(buildApiUrl("/leads/:leadId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const lead = mockDb.leads.find((item) => item.id === params.leadId);
    if (!lead) {
      return HttpResponse.json(
        { error: { code: "LEAD_NOT_FOUND", message: `No lead with id ${String(params.leadId)}` } },
        { status: 404 },
      );
    }
    return HttpResponse.json(lead);
  }),

  http.post(buildApiUrl("/leads"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const body: unknown = await request.json();
    const parsed = createLeadRequestSchema.safeParse(body);
    if (!parsed.success) {
      return HttpResponse.json(
        {
          error: {
            code: "VALIDATION_FAILED",
            message: "The lead could not be saved.",
            details: { issues: parsed.error.issues.length },
          },
        },
        { status: 422 },
      );
    }

    const input = parsed.data;
    if (mockDb.leads.some((lead) => lead.phone === input.phone)) {
      return HttpResponse.json(
        {
          error: {
            code: "DUPLICATE_PHONE",
            message: "A lead with this phone number already exists.",
            details: { fields: { phone: "A lead with this phone number already exists." } },
          },
        },
        { status: 422 },
      );
    }

    const now = new Date().toISOString();
    const sequence = 10_001 + mockDb.leads.length;
    const lead: Lead = {
      id: `lead-${String(sequence)}`,
      code: `LD-26-${String(sequence)}`,
      customerName: input.customerName,
      phone: input.phone,
      village: input.village === "" ? null : input.village,
      district: input.district,
      state: input.state,
      source: input.source,
      type: input.type,
      status: "new",
      estimatedValue: input.estimatedValue,
      winProbability: 15,
      crops: [],
      acreage: null,
      owner: { id: "usr-001", name: "Aarav Desai", avatarUrl: null },
      channelPartner: null,
      engagement: Array.from({ length: 12 }, () => 0),
      followUpAt: null,
      lastActivityAt: now,
      lostReason: null,
      createdAt: now,
      updatedAt: now,
    };
    mockDb.leads = [lead, ...mockDb.leads];
    return HttpResponse.json(lead, { status: 201 });
  }),
];
