import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * TRK-006, TRK-007 · Tracking settings and the view log (`field-tracking-contract.md` §3 Admin).
 * The policy is effective-dated: a save adds a version from `effective_from` and never edits
 * one. The bounds are the backend's (`api/schemas/tracking.py`, `PolicyIn`).
 */

const isoDateTime = z.iso.datetime({ offset: true });

export const POLICY_BOUNDS = {
  intervalSeconds: { min: 15, max: 3600 },
  distanceFilterM: { min: 0, max: 5000 },
  retentionDays: { min: 7, max: 3650 },
  consentTextMax: 10_000,
} as const;

/** Letters, digits, dot, dash or underscore, up to 20: "v1", "2026-10". */
export const CONSENT_VERSION_PATTERN = /^[A-Za-z0-9._-]{1,20}$/;

const policyWireSchema = z.object({
  effective_from: isoDateTime,
  interval_seconds: z.number().int().positive(),
  distance_filter_m: z.number().int().nonnegative(),
  working_hours: z.object({
    start: z.string(),
    end: z.string(),
    days: z.array(z.number().int().min(1).max(7)),
    timezone: z.string().optional(),
  }),
  /** Location points older than this are deleted nightly. */
  retention_days: z.number().int().positive(),
  visit_photo_required: z.boolean(),
  consent_version: z.string(),
  consent_text: z.string(),
});
export type PolicyWire = z.input<typeof policyWireSchema>;

export const policySchema = z.object({ data: policyWireSchema }).transform(({ data }) => ({
  effectiveFrom: data.effective_from,
  intervalSeconds: data.interval_seconds,
  distanceFilterM: data.distance_filter_m,
  /** "HH:MM", India. */
  workStart: data.working_hours.start.slice(0, 5),
  workEnd: data.working_hours.end.slice(0, 5),
  /** ISO weekdays: 1 is Monday. */
  workDays: [...data.working_hours.days].sort((left, right) => left - right),
  retentionDays: data.retention_days,
  visitPhotoRequired: data.visit_photo_required,
  consentVersion: data.consent_version,
  consentText: data.consent_text,
}));
export type Policy = z.output<typeof policySchema>;

export interface PolicyRequest {
  readonly effective_from: string;
  readonly interval_seconds: number;
  readonly distance_filter_m: number;
  readonly work_start: string;
  readonly work_end: string;
  readonly work_days: readonly number[];
  readonly retention_days: number;
  readonly visit_photo_required: boolean;
  readonly consent_version: string;
  readonly consent_text: string;
}

export const VIEW_KINDS = ["route", "visits", "team"] as const;
export type ViewKind = (typeof VIEW_KINDS)[number];

const userRef = z.object({ id: z.string().min(1), full_name: z.string() });

const viewLogRowWireSchema = z.object({
  viewer: userRef,
  /** Null for the team map. */
  subject: userRef.nullable(),
  what: z.enum(VIEW_KINDS),
  viewed_date: z.string().nullable(),
  viewed_at: isoDateTime,
});
export type ViewLogRowWire = z.input<typeof viewLogRowWireSchema>;

const viewLogRowSchema = viewLogRowWireSchema.transform((row) => ({
  viewer: { id: row.viewer.id, name: row.viewer.full_name },
  subject: row.subject === null ? null : { id: row.subject.id, name: row.subject.full_name },
  what: row.what,
  viewedDate: row.viewed_date,
  viewedAt: row.viewed_at,
}));
export type ViewLogRow = z.output<typeof viewLogRowSchema>;

export const viewLogPageSchema = cursorPageSchema(viewLogRowSchema);
export type ViewLogPage = CursorPage<ViewLogRow>;
export type ViewLogPageWire = { data: ViewLogRowWire[]; meta: PageMetaWire };
