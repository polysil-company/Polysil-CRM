import { z } from "zod";

import type { ApplicationStatus } from "./subsidy-applications.schemas";

/**
 * SUBS-009 … SUBS-011 · The subsidy reports (`backend/docs/api/subsidy-reports.md`, handover
 * `subsidy-reports-and-masters.md`): the client's six ageing figures, the stage dashboard and
 * supply by district. Money stays a decimal string; days are whole numbers.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();

export const AGEING_PAGE_SIZE = 50;

/** The six figures, in the order the client's sheet prints them. */
export const AGEING_FIGURES = [
  "today_to_supply",
  "inward_to_submission",
  "wo_to_tpa_received",
  "tpa_cleared_to_inspection_sent",
  "inspection_sent_to_tr",
  "fp_submitted_to_full_fp",
] as const;

export type AgeingFigureKey = (typeof AGEING_FIGURES)[number];

const ageFigureSchema = z
  .object({
    /** Null until the start date is recorded. */
    days: z.number().int().nullable(),
    /** No end yet: counted to today. */
    running: z.boolean(),
    since: isoDate.nullable(),
    until: isoDate.nullable(),
  })
  .transform((wire) => ({
    days: wire.days,
    running: wire.running,
    since: wire.since,
    until: wire.until,
  }));

export type AgeFigure = z.output<typeof ageFigureSchema>;

const ageRowWireSchema = z.object({
  application: z.object({
    id,
    application_no: z.string(),
    reg_no: z.string().nullable(),
    farmer_name: z.string(),
    status: z.string(),
    /** The current stage's name. */
    stage: z.string(),
    district: z.string().nullable(),
  }),
  today_to_supply: ageFigureSchema,
  inward_to_submission: ageFigureSchema,
  wo_to_tpa_received: ageFigureSchema,
  tpa_cleared_to_inspection_sent: ageFigureSchema,
  inspection_sent_to_tr: ageFigureSchema,
  fp_submitted_to_full_fp: ageFigureSchema,
});

export type AgeRowWire = z.input<typeof ageRowWireSchema>;

const ageRowSchema = ageRowWireSchema.transform((wire) => ({
  application: {
    id: wire.application.id,
    number: wire.application.application_no,
    regNo: wire.application.reg_no,
    farmerName: wire.application.farmer_name,
    status: wire.application.status,
    stage: wire.application.stage,
    district: wire.application.district,
  },
  figures: {
    today_to_supply: wire.today_to_supply,
    inward_to_submission: wire.inward_to_submission,
    wo_to_tpa_received: wire.wo_to_tpa_received,
    tpa_cleared_to_inspection_sent: wire.tpa_cleared_to_inspection_sent,
    inspection_sent_to_tr: wire.inspection_sent_to_tr,
    fp_submitted_to_full_fp: wire.fp_submitted_to_full_fp,
  } satisfies Record<AgeingFigureKey, AgeFigure>,
}));

export type AgeRow = z.output<typeof ageRowSchema>;

/** Unknown keys (limit, total) are dropped; only the cursor is read. */
const metaSchema = z.object({ next_cursor: z.string().min(1).nullish() });

export const ageingPageSchema = z
  .object({ data: z.array(ageRowSchema), meta: metaSchema })
  .transform(({ data, meta }) => ({ items: data, nextCursor: meta.next_cursor ?? null }));

export type AgeingPage = z.output<typeof ageingPageSchema>;

export interface AgeingParams {
  readonly status: ApplicationStatus | null;
  readonly stage: string | null;
  readonly q: string;
}

const stageRowWireSchema = z.object({
  seq: z.number().int(),
  code: z.string().min(1),
  name: z.string(),
  count: z.number().int().nonnegative(),
  total_cost: decimal,
  subsidy: decimal,
  farmer_share: decimal,
  oldest_days_in_stage: z.number().int().nullable(),
});

export type StageRowWire = z.input<typeof stageRowWireSchema>;

export const stageReportSchema = z
  .object({ data: z.array(stageRowWireSchema), meta: metaSchema })
  .transform(({ data }) =>
    data.map((row) => ({
      seq: row.seq,
      code: row.code,
      name: row.name,
      count: row.count,
      totalCost: row.total_cost,
      subsidy: row.subsidy,
      farmerShare: row.farmer_share,
      oldestDays: row.oldest_days_in_stage,
    })),
  );

export type StageReportRow = z.output<typeof stageReportSchema>[number];

const supplyRowWireSchema = z.object({
  district: z.string(),
  supplied: z.number().int().nonnegative(),
  not_supplied: z.number().int().nonnegative(),
  supplied_cost: decimal,
  not_supplied_cost: decimal,
});

export type SupplyRowWire = z.input<typeof supplyRowWireSchema>;

export const supplyReportSchema = z
  .object({ data: z.array(supplyRowWireSchema), meta: metaSchema })
  .transform(({ data }) =>
    data.map((row) => ({
      district: row.district,
      supplied: row.supplied,
      notSupplied: row.not_supplied,
      suppliedCost: row.supplied_cost,
      notSuppliedCost: row.not_supplied_cost,
    })),
  );

export type SupplyReportRow = z.output<typeof supplyReportSchema>[number];
