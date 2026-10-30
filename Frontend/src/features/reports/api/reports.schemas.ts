import { z } from "zod";

/**
 * RPT-002, RPT-003 · The reports and a lead's 360° view (`backend/docs/handover/reports-contract.md`,
 * read against `api/services/reports.py`). Every report answers
 * `{ data: { rows, totals, truncated, filters } }`; at most 1,000 rows, with totals over all.
 * A figure the user may not see is null, never 0. Money and percentages are decimal strings.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const count = z.number().int().nonnegative();
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const REPORT_NAMES = [
  "lead-conversion",
  "salesperson-performance",
  "lost-leads",
  "follow-ups",
  "dealer-performance",
  "campaign-performance",
  "territory-performance",
  "complaints",
] as const;

export type ReportName = (typeof REPORT_NAMES)[number];

/** The most rows a report returns; past it `truncated` is true and the totals still count all. */
export const REPORT_ROW_CAP = 1000;

/** The longest window a report takes, in days (backend `domain.window`). */
export const REPORT_MAX_DAYS = 366;

/** Up to 20 territories, as on the lists. */
export const REPORT_MAX_TERRITORIES = 20;

const filtersSchema = z
  .object({
    from: isoDate.optional(),
    to: isoDate.optional(),
    /** Follow-ups only: the moment the figures were taken. */
    as_of: isoDateTime.optional(),
    territory_id: z.array(id).nullish(),
    owner_id: id.nullish(),
    /** Unknown modes are kept and shown as sent. */
    sale_counted_at: z.string().min(1).optional(),
  })
  .transform((wire) => ({
    from: wire.from ?? null,
    to: wire.to ?? null,
    asOf: wire.as_of ?? null,
    saleCountedAt: wire.sale_counted_at ?? null,
  }));

/** A row's group: a source, person, territory, reason or complaint type. Null id: unassigned. */
const keySchema = z.object({ id: id.nullable(), label: z.string() });

const personSchema = z
  .object({ id: id.nullable(), full_name: z.string() })
  .transform((wire) => ({ id: wire.id, name: wire.full_name }));

function reportSchema<Row extends z.ZodType, Totals extends z.ZodType>(
  row: Row,
  totals: Totals,
): z.ZodObject<{
  data: z.ZodObject<{
    rows: z.ZodArray<Row>;
    totals: Totals;
    truncated: z.ZodBoolean;
    filters: typeof filtersSchema;
  }>;
}> {
  return z.object({
    data: z.object({ rows: z.array(row), totals, truncated: z.boolean(), filters: filtersSchema }),
  });
}

// ── lead conversion ───────────────────────────────────────────────────────────────

const conversionRowSchema = z
  .object({
    key: keySchema,
    leads: count,
    contacted: count,
    qualified: count,
    quoted: count,
    won: count,
    lost: count,
    open: count,
    conversion_pct: decimal,
  })
  .transform((wire) => ({
    key: wire.key,
    leads: wire.leads,
    contacted: wire.contacted,
    qualified: wire.qualified,
    quoted: wire.quoted,
    won: wire.won,
    lost: wire.lost,
    open: wire.open,
    conversionPct: wire.conversion_pct,
  }));

const conversionTotalsSchema = z
  .object({ leads: count, won: count, conversion_pct: decimal })
  .transform((wire) => ({ leads: wire.leads, won: wire.won, conversionPct: wire.conversion_pct }));

// ── salesperson performance ──────────────────────────────────────────────────────

const salespersonRowSchema = z
  .object({
    user: personSchema,
    leads_created: count,
    leads_won: count,
    quotations_sent: count.nullable(),
    orders: count.nullable(),
    order_value: decimal.nullable(),
    visits: count.nullable(),
    tasks_done: count.nullable(),
    tasks_overdue: count.nullable(),
  })
  .transform((wire) => ({
    user: wire.user,
    leadsCreated: wire.leads_created,
    leadsWon: wire.leads_won,
    quotationsSent: wire.quotations_sent,
    orders: wire.orders,
    orderValue: wire.order_value,
    visits: wire.visits,
    tasksDone: wire.tasks_done,
    tasksOverdue: wire.tasks_overdue,
  }));

const salespersonTotalsSchema = z
  .object({ leads_created: count, leads_won: count })
  .transform((wire) => ({ leadsCreated: wire.leads_created, leadsWon: wire.leads_won }));

// ── lost leads ───────────────────────────────────────────────────────────────────

const lostRowSchema = z
  .object({
    key: keySchema,
    count,
    share_pct: decimal,
    avg_days_to_loss: decimal.nullable(),
    /** Where they dropped off: a lead stage, or "unknown". */
    by_stage: z.record(z.string(), count),
  })
  .transform((wire) => ({
    key: wire.key,
    count: wire.count,
    sharePct: wire.share_pct,
    avgDaysToLoss: wire.avg_days_to_loss,
    byStage: wire.by_stage,
  }));

const lostTotalsSchema = z.object({ lost: count });

// ── follow-ups ───────────────────────────────────────────────────────────────────

const followUpRowSchema = z
  .object({
    user: personSchema,
    due_today: count,
    overdue_1_2: count,
    overdue_3_7: count,
    overdue_8_30: count,
    overdue_31_plus: count,
    oldest_due_at: isoDateTime.nullable(),
  })
  .transform((wire) => ({
    user: wire.user,
    dueToday: wire.due_today,
    overdue1to2: wire.overdue_1_2,
    overdue3to7: wire.overdue_3_7,
    overdue8to30: wire.overdue_8_30,
    overdue31Plus: wire.overdue_31_plus,
    oldestDueAt: wire.oldest_due_at,
  }));

const followUpTotalsSchema = z
  .object({
    due_today: count,
    overdue_1_2: count,
    overdue_3_7: count,
    overdue_8_30: count,
    overdue_31_plus: count,
  })
  .transform((wire) => ({
    dueToday: wire.due_today,
    overdue1to2: wire.overdue_1_2,
    overdue3to7: wire.overdue_3_7,
    overdue8to30: wire.overdue_8_30,
    overdue31Plus: wire.overdue_31_plus,
  }));

// ── dealer performance ───────────────────────────────────────────────────────────

const dealerRowSchema = z
  .object({
    partner: z.object({ id, name: z.string() }),
    orders: count,
    order_value: decimal,
    dispatched_value: decimal,
    leads_assigned: count.nullable(),
    /** All time, not windowed. */
    received: decimal.nullable(),
    balance: decimal.nullable(),
    complaints: count.nullable(),
  })
  .transform((wire) => ({
    partner: wire.partner,
    orders: wire.orders,
    orderValue: wire.order_value,
    dispatchedValue: wire.dispatched_value,
    leadsAssigned: wire.leads_assigned,
    received: wire.received,
    balance: wire.balance,
    complaints: wire.complaints,
  }));

const dealerTotalsSchema = z
  .object({ orders: count, order_value: decimal })
  .transform((wire) => ({ orders: wire.orders, orderValue: wire.order_value }));

// ── campaign performance ─────────────────────────────────────────────────────────

const campaignRowSchema = z
  .object({
    campaign: z.object({
      id,
      name: z.string(),
      type: z.string(),
      start_date: isoDate,
      end_date: isoDate.nullable(),
      is_active: z.boolean(),
    }),
    leads: count,
    qualified: count,
    won: count,
    lost: count,
    open: count,
    conversion_pct: decimal,
    sales_count: count.nullable(),
    sales_value: decimal.nullable(),
    cost_planned: decimal.nullable(),
    cost_actual: decimal.nullable(),
    cost: decimal.nullable(),
    cost_per_lead: decimal.nullable(),
    cost_per_won: decimal.nullable(),
  })
  .transform((wire) => ({
    campaign: {
      id: wire.campaign.id,
      name: wire.campaign.name,
      type: wire.campaign.type,
      startDate: wire.campaign.start_date,
      endDate: wire.campaign.end_date,
      isActive: wire.campaign.is_active,
    },
    leads: wire.leads,
    qualified: wire.qualified,
    won: wire.won,
    lost: wire.lost,
    open: wire.open,
    conversionPct: wire.conversion_pct,
    salesCount: wire.sales_count,
    salesValue: wire.sales_value,
    cost: wire.cost,
    costPerLead: wire.cost_per_lead,
    costPerWon: wire.cost_per_won,
  }));

const campaignTotalsSchema = z
  .object({
    leads: count,
    won: count,
    sales_value: decimal.nullable(),
    cost: decimal.nullable(),
  })
  .transform((wire) => ({
    leads: wire.leads,
    won: wire.won,
    salesValue: wire.sales_value,
    cost: wire.cost,
  }));

// ── territory performance ────────────────────────────────────────────────────────

const territoryRowSchema = z
  .object({
    /** Null id: leads sitting above the chosen level. */
    territory: z.object({ id: id.nullable(), name: z.string() }),
    leads: count,
    won: count,
    conversion_pct: decimal,
    orders: count.nullable(),
    order_value: decimal.nullable(),
  })
  .transform((wire) => ({
    territory: wire.territory,
    leads: wire.leads,
    won: wire.won,
    conversionPct: wire.conversion_pct,
    orders: wire.orders,
    orderValue: wire.order_value,
  }));

const territoryTotalsSchema = z.object({ leads: count, won: count });

// ── complaints ───────────────────────────────────────────────────────────────────

const complaintRowSchema = z
  .object({
    key: keySchema,
    count,
    resolved: count,
    resolved_within_sla_pct: decimal,
    response_breaches: count,
  })
  .transform((wire) => ({
    key: wire.key,
    count: wire.count,
    resolved: wire.resolved,
    resolvedWithinSlaPct: wire.resolved_within_sla_pct,
    responseBreaches: wire.response_breaches,
  }));

const complaintTotalsSchema = z.object({
  count,
  resolved: count,
  refunds: z.object({ count, amount: decimal }),
});

/** Each report's answer, by name. */
export const REPORT_SCHEMAS = {
  "lead-conversion": reportSchema(conversionRowSchema, conversionTotalsSchema),
  "salesperson-performance": reportSchema(salespersonRowSchema, salespersonTotalsSchema),
  "lost-leads": reportSchema(lostRowSchema, lostTotalsSchema),
  "follow-ups": reportSchema(followUpRowSchema, followUpTotalsSchema),
  "dealer-performance": reportSchema(dealerRowSchema, dealerTotalsSchema),
  "campaign-performance": reportSchema(campaignRowSchema, campaignTotalsSchema),
  "territory-performance": reportSchema(territoryRowSchema, territoryTotalsSchema),
  complaints: reportSchema(complaintRowSchema, complaintTotalsSchema),
} as const;

export type ReportData<N extends ReportName> = z.output<(typeof REPORT_SCHEMAS)[N]>["data"];

export type ReportWire<N extends ReportName> = z.input<(typeof REPORT_SCHEMAS)[N]>["data"];

/** What the screen asks a report for; each report sends only the filters it takes. */
export interface ReportParams {
  /** Indian dates, inclusive; null for the backend's default (the last 30 days). */
  readonly from: string | null;
  readonly to: string | null;
  readonly territories: readonly string[];
  readonly owner: string | null;
  /** `group_by`, or `level` on the territory report; null for the report's default. */
  readonly groupBy: string | null;
}

// ── the 360° lead view (RPT-003) ─────────────────────────────────────────────────

export const lead360Schema = z
  .object({
    data: z.object({
      lead: z.object({
        id,
        inquiry_no: z.string(),
        farmer_name: z.string(),
        mobile: z.string(),
        stage: z.string(),
      }),
      related_leads: z.array(
        z.object({
          id,
          inquiry_no: z.string(),
          stage: z.string(),
          relation: z.string(),
        }),
      ),
      summary: z.object({
        quotations: count.nullable(),
        orders: count.nullable(),
        order_value: decimal.nullable(),
        received: decimal.nullable(),
        complaints: count.nullable(),
        visits: count.nullable(),
        open_tasks: count.nullable(),
        /** The application's current stage number. */
        subsidy_stage: z.number().int().nullable(),
      }),
    }),
  })
  .transform(({ data }) => ({
    relatedLeads: data.related_leads.map((lead) => ({
      id: lead.id,
      inquiryNo: lead.inquiry_no,
      stage: lead.stage,
      relation: lead.relation,
    })),
    summary: {
      quotations: data.summary.quotations,
      orders: data.summary.orders,
      orderValue: data.summary.order_value,
      received: data.summary.received,
      complaints: data.summary.complaints,
      visits: data.summary.visits,
      openTasks: data.summary.open_tasks,
      subsidyStage: data.summary.subsidy_stage,
    },
  }));

export type Lead360 = z.output<typeof lead360Schema>;
export type Lead360Wire = z.input<typeof lead360Schema>["data"];
