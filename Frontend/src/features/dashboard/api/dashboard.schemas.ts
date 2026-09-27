import { z } from "zod";

import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";

// TODO(RPT-001): agree the dashboard contract with the backend developer.

const isoDateTime = z.iso.datetime({ offset: true });

const kpiSchema = z.object({
  value: z.number(),
  /** Change vs the previous period, in percent. Null when there is no previous period. */
  deltaPercent: z.number().nullable(),
  /** Oldest first. */
  trend: z.array(z.number()),
});

export const dashboardOverviewSchema = z.object({
  periodLabel: z.string().min(1),
  kpis: z.object({
    pipelineValue: kpiSchema,
    newLeads: kpiSchema,
    conversionRate: kpiSchema,
    overdueFollowUps: kpiSchema,
  }),
  pipeline: z.array(
    z.object({
      status: z.enum(LEAD_STAGES),
      count: z.number().int().nonnegative(),
      value: z.number().nonnegative(),
    }),
  ),
  sources: z.array(
    z.object({
      /** A lead-source code; `name` comes with it, since administrators edit the list. */
      source: z.string().min(1),
      name: z.string().min(1),
      count: z.number().int().nonnegative(),
    }),
  ),
  followUps: z.array(
    z.object({
      leadId: z.string().min(1),
      customerName: z.string().min(1),
      district: z.string().min(1),
      dueAt: isoDateTime,
      ownerName: z.string().min(1),
    }),
  ),
});

export type DashboardOverview = z.infer<typeof dashboardOverviewSchema>;
