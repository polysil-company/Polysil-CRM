import { z } from "zod";

/**
 * TGT-001, TGT-002 · Monthly targets per person, and achievement live
 * (`backend/docs/handover/targets-contract.md`, read against `api/services/targets.py`).
 * Months are `YYYY-MM`. Order value is a decimal string in rupees; the other three are whole
 * numbers. `achieved` is null for a measure the user may not see; `pct` is null without a
 * target (or without the achieved figure).
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const count = z.number().int().nonnegative();
const isoDateTime = z.iso.datetime({ offset: true });
const month = z.string().regex(/^\d{4}-\d{2}$/);

export const TARGET_METRICS = ["order_value", "orders", "leads_won", "visits"] as const;
export type TargetMetric = (typeof TARGET_METRICS)[number];

const personSchema = z
  .object({ id, full_name: z.string() })
  .transform((wire) => ({ id: wire.id, name: wire.full_name.trim() || "Unnamed" }));

/** A figure, in rupees for order value and a count for the others; null when not set or hidden. */
const figure = z.union([decimal, count]).nullable();

const measureSchema = z.object({ target: figure, achieved: figure, pct: decimal.nullable() });

export type Measure = z.output<typeof measureSchema>;

const measuresSchema = z.object({
  order_value: measureSchema,
  orders: measureSchema,
  leads_won: measureSchema,
  visits: measureSchema,
});

export const achievementSchema = z
  .object({
    data: z.object({
      month,
      as_of: isoDateTime,
      rows: z.array(z.object({ user: personSchema, metrics: measuresSchema })),
      totals: measuresSchema,
      filters: z.object({ sale_counted_at: z.string().min(1).optional() }).optional(),
    }),
  })
  .transform(({ data }) => ({
    month: data.month,
    asOf: data.as_of,
    rows: data.rows,
    totals: data.totals,
    saleCountedAt: data.filters?.sale_counted_at ?? null,
  }));

export type Achievement = z.output<typeof achievementSchema>;
export type AchievementWire = z.input<typeof achievementSchema>["data"];

export const personTargetsSchema = z
  .object({
    data: z.object({
      user: personSchema,
      month,
      targets: z.object({
        order_value: decimal.nullable(),
        orders: count.nullable(),
        leads_won: count.nullable(),
        visits: count.nullable(),
      }),
      history: z.array(
        z.object({
          metric: z.string().min(1),
          value: z.union([decimal, count]),
          /** The setter's name is blank for a reader without users.view (GAP-228). */
          set_by: z.object({ id: id.nullable(), full_name: z.string() }),
          set_at: isoDateTime,
        }),
      ),
    }),
  })
  .transform(({ data }) => ({
    user: data.user,
    month: data.month,
    targets: {
      orderValue: data.targets.order_value,
      orders: data.targets.orders,
      leadsWon: data.targets.leads_won,
      visits: data.targets.visits,
    },
    history: data.history.map((entry) => ({
      metric: entry.metric,
      value: entry.value,
      setBy: entry.set_by.full_name.trim() || null,
      setAt: entry.set_at,
    })),
  }));

export type PersonTargets = z.output<typeof personTargetsSchema>;
export type PersonTargetsWire = z.input<typeof personTargetsSchema>["data"];

/** PUT /targets: only the measures that change; 0 clears one. */
export interface SetTargetsRequest {
  readonly user_id: string;
  readonly month: string;
  readonly targets: Partial<Record<TargetMetric, string | number>>;
}
