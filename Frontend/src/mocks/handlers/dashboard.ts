import { http, HttpResponse } from "msw";

import type { DashboardOverview } from "@/features/dashboard/api/dashboard.schemas";
import type { LeadStage, LeadWire } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { sumRupees, toRupeeNumber } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

const DAY = 24 * 60 * 60 * 1000;

/** The funnel the dashboard draws; merged and dormant leads are not part of it. */
const PIPELINE_STAGES: readonly LeadStage[] = [
  "new",
  "contacted",
  "qualified",
  "quoted",
  "negotiation",
  "won",
  "lost",
];

const CLOSED_STAGES: readonly LeadStage[] = ["won", "lost", "merged", "dormant"];

function totalValue(leads: readonly LeadWire[]): number {
  return toRupeeNumber(sumRupees(leads.map((lead) => lead.estimated_value))) ?? 0;
}

/**
 * The backend records no follow-up dates yet (TODO(LEAD-003)); the mock dashboard assumes
 * one three days after the last activity, so the follow-up card has something to show.
 */
function assumedFollowUp(lead: LeadWire): number {
  return Date.parse(lead.last_activity_at) + 3 * DAY;
}

function districtOf(lead: LeadWire): string {
  return findMockTerritory(lead.territory.id)?.district ?? lead.territory.name;
}

export const dashboardHandlers = [
  http.get(buildApiUrl("/dashboard/overview"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const leads = scenario === "empty" ? [] : mockDb.leads;
    const now = Date.now();
    const open = leads.filter((lead) => !CLOSED_STAGES.includes(lead.stage));
    const closed = leads.filter((lead) => lead.stage === "won" || lead.stage === "lost");
    const won = leads.filter((lead) => lead.stage === "won");
    const newThisMonth = leads.filter(
      (lead) => now - Date.parse(lead.created_at) <= 30 * DAY,
    ).length;
    const overdue = open.filter((lead) => assumedFollowUp(lead) < now);

    const weeklyNewLeads = Array.from({ length: 12 }, (_, week) => {
      const end = now - (11 - week) * 7 * DAY;
      return leads.filter((lead) => {
        const created = Date.parse(lead.created_at);
        return created <= end && created > end - 7 * DAY;
      }).length;
    });

    const overview: DashboardOverview = {
      periodLabel: "Last 30 days",
      kpis: {
        pipelineValue: {
          value: totalValue(open),
          deltaPercent: 12.4,
          trend: weeklyNewLeads.map((count) => count * 180_000),
        },
        newLeads: { value: newThisMonth, deltaPercent: 8.1, trend: weeklyNewLeads },
        conversionRate: {
          value: closed.length === 0 ? 0 : (won.length / closed.length) * 100,
          deltaPercent: -2.3,
          trend: [52, 54, 51, 56, 58, 55, 57, 59, 56, 58, 57, 60],
        },
        overdueFollowUps: {
          value: overdue.length,
          deltaPercent: -6.5,
          trend: [14, 13, 15, 12, 11, 12, 10, 11, 9, 10, 9, overdue.length],
        },
      },
      pipeline: PIPELINE_STAGES.map((stage) => {
        const inStage = leads.filter((lead) => lead.stage === stage);
        return { status: stage, count: inStage.length, value: totalValue(inStage) };
      }),
      sources: mockLookupRows("lead-sources").map((source) => ({
        source: source.code,
        name: source.name,
        count: leads.filter((lead) => lead.source === source.code).length,
      })),
      followUps: [...open]
        .sort((a, b) => assumedFollowUp(a) - assumedFollowUp(b))
        .slice(0, 6)
        .map((lead) => ({
          leadId: lead.id,
          customerName: lead.farmer_name,
          district: districtOf(lead),
          dueAt: new Date(assumedFollowUp(lead)).toISOString(),
          ownerName: lead.owner?.full_name ?? "Unassigned",
        })),
    };

    return HttpResponse.json(overview);
  }),
];
