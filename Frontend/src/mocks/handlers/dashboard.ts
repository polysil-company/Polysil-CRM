import { http, HttpResponse } from "msw";

import type { DashboardOverviewWire } from "@/features/dashboard/api/dashboard.schemas";
import type { LeadStage, LeadWire } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { sumRupees, todayInIndia } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { leadInPartnerScope } from "@/mocks/data/partner-scope";
import { mockPermissionsFor } from "@/mocks/data/permissions";
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

/** FS-052: open and won leads now, by irrigation system, in name order; empty systems left out. */
function areaBySystem(leads: readonly LeadWire[]): DashboardOverviewWire["area_by_system"] {
  const counted = leads.filter(
    (lead) => !CLOSED_STAGES.includes(lead.stage) || lead.stage === "won",
  );
  return mockLookupRows("mis-systems")
    .map((system) => {
      const withSystem = counted.filter((lead) => lead.mis_system === system.code);
      const hectares = withSystem.reduce((sum, lead) => sum + Number(lead.land_hectares ?? 0), 0);
      return {
        system: system.code,
        name: system.name,
        leads: withSystem.length,
        hectares: hectares.toFixed(2),
      };
    })
    .filter((system) => system.leads > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** What the team sold against its target, as a share; the last month is under way. */
const MONTH_ACHIEVEMENT: readonly number[] = [0.82, 1.08, 0.64, 0.91, 1.15, 0.38];

/**
 * FS-052: this month and the five before it, oldest first. Null without a targets
 * permission; `achieved` null without a sales orders one, as on the backend.
 */
function targetsByMonth(empty: boolean): DashboardOverviewWire["targets_by_month"] {
  const permissions = mockPermissionsFor(readMockRole());
  if (!can(permissions, "targets")) return null;
  const seesSales = can(permissions, "sales_orders");
  // An officer's own target; a manager's or Admin's is their team's.
  const own = permissions.some((entry) => entry.module === "targets" && entry.scope === "own");
  const target = own ? 600_000 : 2_400_000;
  const [year = 2026, month = 1] = todayInIndia().split("-").map(Number);
  return MONTH_ACHIEVEMENT.map((share, index) => {
    const date = new Date(Date.UTC(year, month - 1 - (5 - index), 1));
    return {
      month: date.toISOString().slice(0, 7),
      target: empty ? "0.00" : target.toFixed(2),
      achieved: seesSales ? (empty ? 0 : target * share).toFixed(2) : null,
    };
  });
}

function districtOf(lead: LeadWire): string | null {
  return findMockTerritory(lead.territory.id)?.district ?? null;
}

export const dashboardHandlers = [
  http.get(buildApiUrl("/dashboard/overview"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const leads = scenario === "empty" ? [] : mockDb.leads.filter(leadInPartnerScope);
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
      area_by_system: areaBySystem(leads),
      targets_by_month: targetsByMonth(scenario === "empty"),
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
