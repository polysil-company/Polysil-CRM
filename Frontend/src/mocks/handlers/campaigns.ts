import { http, HttpResponse } from "msw";
import { z } from "zod";

import { CAMPAIGN_TYPES, type CampaignWire } from "@/features/campaigns/api/campaigns.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockCampaignId, type MockCampaign } from "@/mocks/data/campaigns";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MKT-005, MKT-006 · Campaigns (FS-040, `docs/api/campaigns.md`). Any staff user lists them; a
 * partner gets 403. Cost is null without `campaigns.view`; writes need create, edit or delete.
 */

type Action = "view" | "create" | "edit" | "delete";

function allowed(action: Action): boolean {
  return can(mockPermissionsFor(readMockRole()), "campaigns", action);
}

function staffOnly(): Response | null {
  return isPartnerRole(readMockRole())
    ? errorResponse(403, "forbidden", "Campaigns are for staff.")
    : null;
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

const paise = (value: string): number => Math.round(Number(value) * 100);
const rupees = (value: number): string => (value / 100).toFixed(2);

function leadsOf(campaignId: string): typeof mockDb.leads {
  return mockDb.leads.filter((lead) => lead.campaign_id === campaignId && lead.stage !== "merged");
}

function wireFor(campaign: MockCampaign, withSummary: boolean): CampaignWire {
  const seesCost = allowed("view");
  const leads = leadsOf(campaign.id);
  const cost = paise(campaign.cost_actual ?? campaign.cost_planned ?? "0");
  const won = leads.filter((lead) => lead.stage === "won").length;
  const lost = leads.filter((lead) => lead.stage === "lost").length;
  const ids = new Set(leads.map((lead) => lead.id));
  const sales = mockDb.orders
    .filter(
      (order) =>
        order.lead !== null &&
        ids.has(order.lead.id) &&
        ["approved", "partially_dispatched", "dispatched", "closed_short"].includes(order.status),
    )
    .reduce((sum, order) => sum + paise(order.totals.total), 0);
  return {
    ...campaign,
    cost_planned: seesCost ? campaign.cost_planned : null,
    cost_actual: seesCost ? campaign.cost_actual : null,
    lead_count: leads.length,
    summary: withSummary
      ? {
          leads: leads.length,
          won,
          lost,
          open: leads.length - won - lost,
          sales_value: can(mockPermissionsFor(readMockRole()), "sales_orders", "view")
            ? rupees(sales)
            : null,
          cost_per_lead: seesCost && leads.length > 0 ? rupees(cost / leads.length) : null,
          cost_per_won: seesCost && won > 0 ? rupees(cost / won) : null,
        }
      : null,
  };
}

const money = z
  .union([z.number(), z.string()])
  .transform(String)
  .pipe(z.string().regex(/^\d+(\.\d{1,2})?$/, "Rupees, like 150000 or 150000.50."));

const baseSchema = z.object({
  name: z.string().trim().min(1, "Name it.").max(160),
  type: z.enum(CAMPAIGN_TYPES),
  territory_id: z.string().min(1).nullish(),
  start_date: z.iso.date("A date."),
  end_date: z.iso.date("A date.").nullish(),
  cost_planned: money.default("0"),
  cost_actual: money.nullish(),
  description: z.string().max(2000).nullish(),
});

const patchSchema = baseSchema.partial().extend({ is_active: z.boolean().optional() });

function territoryRef(territoryId: string | null | undefined): CampaignWire["territory"] | "bad" {
  if (territoryId == null) return null;
  const found = findMockTerritory(territoryId);
  return found === undefined ? "bad" : { id: found.id, name: found.name, level: found.level };
}

function nameTaken(name: string, exceptId: string | null): boolean {
  const wanted = name.trim().toLowerCase();
  return mockDb.campaigns.some(
    (campaign) => campaign.id !== exceptId && campaign.name.trim().toLowerCase() === wanted,
  );
}

export const campaignHandlers = [
  http.get(buildApiUrl("/campaigns"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const refused = staffOnly();
    if (refused) return refused;
    const url = new URL(request.url);
    const active = url.searchParams.get("active");
    const type = url.searchParams.get("type");
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const rows = mockDb.campaigns
      .filter((campaign) => active === null || String(campaign.is_active) === active)
      .filter((campaign) => type === null || type === "" || campaign.type === type)
      .filter((campaign) => q === "" || campaign.name.toLowerCase().includes(q))
      .sort((left, right) => right.start_date.localeCompare(left.start_date))
      .slice(0, 500)
      .map((campaign) => wireFor(campaign, false));
    return HttpResponse.json({ data: rows });
  }),

  http.get(buildApiUrl("/campaigns/:campaignId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const refused = staffOnly();
    if (refused) return refused;
    const campaign = mockDb.campaigns.find((item) => item.id === params.campaignId);
    if (campaign === undefined) return errorResponse(404, "not_found", "No such campaign.");
    return HttpResponse.json({ data: wireFor(campaign, true) });
  }),

  http.post(buildApiUrl("/campaigns"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (staffOnly() !== null || !allowed("create")) {
      return errorResponse(403, "forbidden", "Not in your permissions.");
    }
    const parsed = baseSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (body.end_date != null && body.end_date < body.start_date) {
      return invalid({ end_date: "Not before the start." });
    }
    const territory = territoryRef(body.territory_id);
    if (territory === "bad") return invalid({ territory_id: "Not a known territory." });
    if (nameTaken(body.name, null)) {
      return errorResponse(409, "campaign_name_taken", "Another campaign has that name.");
    }
    const now = new Date().toISOString();
    const campaign: MockCampaign = {
      id: mockCampaignId(100 + mockDb.campaigns.length),
      name: body.name,
      type: body.type,
      territory,
      start_date: body.start_date,
      end_date: body.end_date ?? null,
      cost_planned: Number(body.cost_planned).toFixed(2),
      cost_actual: body.cost_actual == null ? null : Number(body.cost_actual).toFixed(2),
      description: body.description?.trim() ? body.description.trim() : null,
      is_active: true,
      created_at: now,
      updated_at: now,
    };
    mockDb.campaigns.push(campaign);
    return HttpResponse.json({ data: wireFor(campaign, false) }, { status: 201 });
  }),

  http.patch(buildApiUrl("/campaigns/:campaignId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (staffOnly() !== null || !allowed("edit")) {
      return errorResponse(403, "forbidden", "Not in your permissions.");
    }
    const campaign = mockDb.campaigns.find((item) => item.id === params.campaignId);
    if (campaign === undefined) return errorResponse(404, "not_found", "No such campaign.");
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const start = body.start_date ?? campaign.start_date;
    const end = body.end_date === undefined ? campaign.end_date : body.end_date;
    if (end != null && end < start) return invalid({ end_date: "Not before the start." });
    if (body.name !== undefined && nameTaken(body.name, campaign.id)) {
      return errorResponse(409, "campaign_name_taken", "Another campaign has that name.");
    }
    if (body.territory_id !== undefined) {
      const territory = territoryRef(body.territory_id);
      if (territory === "bad") return invalid({ territory_id: "Not a known territory." });
      campaign.territory = territory;
    }
    if (body.name !== undefined) campaign.name = body.name;
    if (body.type !== undefined) campaign.type = body.type;
    campaign.start_date = start;
    campaign.end_date = end ?? null;
    if (body.cost_planned !== undefined) {
      campaign.cost_planned = Number(body.cost_planned).toFixed(2);
    }
    if (body.cost_actual !== undefined) {
      campaign.cost_actual = body.cost_actual == null ? null : Number(body.cost_actual).toFixed(2);
    }
    if (body.description !== undefined) {
      campaign.description = body.description?.trim() ? body.description.trim() : null;
    }
    if (body.is_active !== undefined) campaign.is_active = body.is_active;
    campaign.updated_at = new Date().toISOString();
    // A renamed campaign reads with its new name on every lead and code.
    for (const lead of mockDb.leads) {
      if (lead.campaign_id === campaign.id) lead.campaign_name = campaign.name;
    }
    for (const code of mockDb.qrCodes) {
      if (code.campaign_id === campaign.id) code.campaign_name = campaign.name;
    }
    return HttpResponse.json({ data: wireFor(campaign, false) });
  }),

  http.delete(buildApiUrl("/campaigns/:campaignId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (staffOnly() !== null || !allowed("delete")) {
      return errorResponse(403, "forbidden", "Not in your permissions.");
    }
    const index = mockDb.campaigns.findIndex((item) => item.id === params.campaignId);
    if (index === -1) return errorResponse(404, "not_found", "No such campaign.");
    const id = String(params.campaignId);
    const inUse =
      mockDb.leads.some((lead) => lead.campaign_id === id) ||
      mockDb.qrCodes.some((code) => code.campaign_id === id);
    if (inUse) {
      return errorResponse(409, "campaign_in_use", "Leads or QR codes name it. Switch it off.");
    }
    mockDb.campaigns.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
];

/** MKT-006 · Resolves a campaign id sent on a lead or a QR code; null clears, "bad" refuses. */
export function campaignRefFor(
  campaignId: string | null | undefined,
): { id: string; name: string } | null | "bad" {
  if (campaignId == null) return null;
  const campaign = mockDb.campaigns.find((item) => item.id === campaignId);
  return campaign === undefined || !campaign.is_active
    ? "bad"
    : { id: campaign.id, name: campaign.name };
}
