import { http, HttpResponse } from "msw";

import type { DashboardOverviewWire } from "@/features/dashboard/api/dashboard.schemas";
import type { LeadStage, LeadWire } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { sumRupees } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

const DAY = 24 * 60 * 60 * 1000;

/** Every stage but merged, in lifecycle order, as the backend lists them. */
const PIPELINE_STAGES: readonly LeadStage[] = [
  "new",
  "contacted",
  "qualified",
  "quoted",
  "negotiation",
  "won",
  "lost",
  "dormant",
];

const CLOSED_STAGES: readonly LeadStage[] = ["won", "lost", "merged", "dormant"];

function totalValue(leads: readonly LeadWire[]): string {
  return sumRupees(leads.map((lead) => lead.estimated_value));
}

/** A decimal string at one place, as the backend sends percentages and counts. */
function oneDecimal(value: number): string {
  return value.toFixed(1);
}

/**
 * Follow-ups are tasks on the backend; the mock has no tasks yet (TODO(TASK-001)), so it
 * assumes one three days after a lead's last activity, so the card has something to show.
 */
function assumedFollowUp(lead: LeadWire): number {
  return Date.parse(lead.last_activity_at) + 3 * DAY;
}

function districtOf(lead: LeadWire): string | null {
  return findMockTerritory(lead.territory.id)?.district ?? null;
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

    const startOfToday = new Date(now);
    startOfToday.setHours(0, 0, 0, 0);
    const overview: DashboardOverviewWire = {
      period_label: "Last 30 days",
      period: {
        start: new Date(now - 29 * DAY).toISOString().slice(0, 10),
        end: new Date(now).toISOString().slice(0, 10),
      },
      kpis: {
        // Snapshot figures: no change and no trend, as on the backend.
        pipeline_value: { value: totalValue(open), delta_percent: null, trend: [] },
        new_leads: {
          value: String(newThisMonth),
          delta_percent: "8.1",
          trend: weeklyNewLeads.map(String),
        },
        conversion_rate: {
          value: oneDecimal(closed.length === 0 ? 0 : (won.length / closed.length) * 100),
          delta_percent: "-2.3",
          trend: [52, 54, 51, 56, 58, 55, 57, 59, 56, 58, 57, 60].map(oneDecimal),
        },
        overdue_follow_ups: { value: String(overdue.length), delta_percent: null, trend: [] },
      },
      pipeline: PIPELINE_STAGES.map((stage) => {
        const inStage = leads.filter((lead) => lead.stage === stage);
        return { stage, count: inStage.length, value: totalValue(inStage) };
      }),
      sources: mockLookupRows("lead-sources").map((source) => ({
        source: source.code,
        name: source.name,
        count: leads.filter((lead) => lead.source === source.code).length,
      })),
      follow_ups: [...open]
        .sort((a, b) => assumedFollowUp(a) - assumedFollowUp(b))
        .slice(0, 10)
        .map((lead, index) => ({
          task_id: `${lead.id}-follow-up-${String(index)}`,
          lead_id: lead.id,
          farmer_name: lead.farmer_name,
          district: districtOf(lead),
          due_at: new Date(assumedFollowUp(lead)).toISOString(),
          assigned_to: lead.owner,
          overdue: assumedFollowUp(lead) < startOfToday.getTime(),
        })),
    };

    return HttpResponse.json({ data: overview });
  }),
];
