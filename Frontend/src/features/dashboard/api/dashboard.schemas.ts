import { z } from "zod";

import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";

/**
 * RPT-001 · `GET /dashboard/overview`, as the backend serves it since BE-008
 * (backend/docs/api/dashboard.md). Every figure is a decimal string: money stays a string
 * all the way to the formatter; counts and percentages become numbers only for display and
 * for drawing the sparklines.
 */

const isoDateTime = z.iso.datetime({ offset: true });
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

const kpiWireSchema = z.object({
  /** Null only for overdue follow-ups when the role has no task permission. */
  value: decimal.nullable(),
  /** One decimal; null when the previous period was zero, and always for a snapshot figure. */
  delta_percent: decimal.nullable(),
  /** Oldest first, one per bucket of the period; empty for a snapshot figure. */
  trend: z.array(decimal),
});

const kpiSchema = kpiWireSchema.transform((wire) => ({
  value: wire.value,
  deltaPercent: wire.delta_percent,
  trend: wire.trend,
}));

export type DashboardKpi = z.output<typeof kpiSchema>;

const dashboardOverviewWireSchema = z.object({
  period_label: z.string().min(1),
  period: z.object({ start: isoDate, end: isoDate }),
  kpis: z.object({
    pipeline_value: kpiSchema,
    new_leads: kpiSchema,
    conversion_rate: kpiSchema,
    overdue_follow_ups: kpiSchema,
  }),
  /** Every stage but merged, in lifecycle order. */
  pipeline: z.array(
    z.object({
      stage: z.enum(LEAD_STAGES),
      count: z.number().int().nonnegative(),
      value: decimal,
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
  /** The 10 earliest-due open tasks on the user's leads; empty without a task permission. */
  follow_ups: z.array(
    z.object({
      task_id: z.string().min(1),
      lead_id: z.string().min(1),
      farmer_name: z.string(),
      district: z.string().nullable(),
      due_at: isoDateTime,
      /** `full_name` is empty for someone outside the user's view of people. */
      assigned_to: z.object({ id: z.string().min(1), full_name: z.string() }).nullable(),
      overdue: z.boolean(),
    }),
  ),
});

export type DashboardOverviewWire = z.input<typeof dashboardOverviewWireSchema>;

/** `{ data: DashboardOverview }`, read into the shape the screen draws. */
export const dashboardOverviewSchema = z
  .object({ data: dashboardOverviewWireSchema })
  .transform(({ data }) => ({
    periodLabel: data.period_label,
    period: data.period,
    kpis: {
      pipelineValue: data.kpis.pipeline_value,
      newLeads: data.kpis.new_leads,
      conversionRate: data.kpis.conversion_rate,
      overdueFollowUps: data.kpis.overdue_follow_ups,
    },
    pipeline: data.pipeline,
    sources: data.sources,
    followUps: data.follow_ups.map((item) => ({
      taskId: item.task_id,
      leadId: item.lead_id,
      customerName: item.farmer_name.trim() || "Unnamed customer",
      district: item.district,
      dueAt: item.due_at,
      ownerName: item.assigned_to?.full_name.trim() || null,
      overdue: item.overdue,
    })),
  }));

export type DashboardOverview = z.output<typeof dashboardOverviewSchema>;

/** A count or percentage from a decimal string, for display and sparklines; never money. */
export function figure(value: string | null): number | null {
  if (value === null) {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/** A trend's points as numbers, for drawing only. */
export function trendPoints(trend: readonly string[]): number[] {
  return trend.map(Number).filter((point) => Number.isFinite(point));
}
