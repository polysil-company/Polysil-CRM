import { http, HttpResponse } from "msw";

import type { DashboardOverview } from "@/features/dashboard/api/dashboard.schemas";
import { LEAD_SOURCES, LEAD_STATUSES } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

const DAY = 24 * 60 * 60 * 1000;

export const dashboardHandlers = [
  http.get(buildApiUrl("/dashboard/overview"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const leads = scenario === "empty" ? [] : mockDb.leads;
    const now = Date.now();
    const open = leads.filter((lead) => lead.status !== "won" && lead.status !== "lost");
    const closed = leads.filter((lead) => lead.status === "won" || lead.status === "lost");
    const won = leads.filter((lead) => lead.status === "won");
    const pipelineValue = open.reduce((sum, lead) => sum + (lead.estimatedValue ?? 0), 0);
    const newThisMonth = leads.filter(
      (lead) => now - Date.parse(lead.createdAt) <= 30 * DAY,
    ).length;
    const overdue = open.filter(
      (lead) => lead.followUpAt !== null && Date.parse(lead.followUpAt) < now,
    );

    const weeklyNewLeads = Array.from({ length: 12 }, (_, week) => {
      const end = now - (11 - week) * 7 * DAY;
      return leads.filter((lead) => {
        const created = Date.parse(lead.createdAt);
        return created <= end && created > end - 7 * DAY;
      }).length;
    });

    const overview: DashboardOverview = {
      periodLabel: "Last 30 days",
      kpis: {
        pipelineValue: {
          value: pipelineValue,
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
      pipeline: LEAD_STATUSES.map((status) => {
        const inStatus = leads.filter((lead) => lead.status === status);
        return {
          status,
          count: inStatus.length,
          value: inStatus.reduce((sum, lead) => sum + (lead.estimatedValue ?? 0), 0),
        };
      }),
      sources: LEAD_SOURCES.map((source) => ({
        source,
        count: leads.filter((lead) => lead.source === source).length,
      })),
      followUps: open
        .filter((lead) => lead.followUpAt !== null)
        .sort((a, b) => Date.parse(a.followUpAt ?? "") - Date.parse(b.followUpAt ?? ""))
        .slice(0, 6)
        .map((lead) => ({
          leadId: lead.id,
          customerName: lead.customerName,
          district: lead.district,
          dueAt: lead.followUpAt ?? new Date(now).toISOString(),
          ownerName: lead.owner.name,
        })),
    };

    return HttpResponse.json(overview);
  }),
];
