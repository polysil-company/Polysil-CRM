import { z } from "zod";

import type { LookupList } from "@/features/lookups/api/lookups.schemas";

/**
 * MSTR-009, MSTR-010 · Writing the admin lists and the lead score's settings
 * (backend/docs/api/lookups.md). Rows are added and switched off, never renamed or deleted,
 * so a lead keeps the reason it was lost with (ADR-033).
 */

const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

/** One list row, as a write answers it. Reads come from MSTR-002's `lookupListResponseSchema`. */
export const lookupItemResponseSchema = z
  .object({
    data: z.object({
      id: z.string().min(1),
      code: z.string().min(1),
      name: z.string().min(1),
      is_active: z.boolean().optional(),
    }),
  })
  .transform(({ data }) => ({
    id: data.id,
    code: data.code,
    name: data.name,
    isActive: data.is_active ?? true,
  }));

export type LookupItemResponse = z.input<typeof lookupItemResponseSchema>;

/** A code: lowercase letters, digits and underscores; it never changes once added. */
export const LOOKUP_CODE_PATTERN = /^[a-z0-9_]+$/;
export const LOOKUP_CODE_MAX_LENGTH = 50;
export const LOOKUP_NAME_MAX_LENGTH = 100;

/** Which lists take which extra fields when a row is added. */
export function listTakesSortOrder(list: LookupList): boolean {
  return list === "lead-sources" || list === "lost-reasons";
}

export function listTakesQuality(list: LookupList): boolean {
  return list === "lead-sources";
}

export function listTakesKind(list: LookupList): boolean {
  return list === "lost-reasons";
}

/** POST /lookups/{list}. `sort_order` for sources and reasons; `quality` sources; `kind` reasons. */
export interface LookupCreateRequest {
  readonly code: string;
  readonly name: string;
  readonly sort_order?: number;
  readonly quality?: string;
  readonly kind?: "won" | "lost";
}

/** PATCH /lookups/{list}/{id}: switch on or off, reorder, or a source's quality. */
export interface LookupUpdateRequest {
  readonly is_active?: boolean;
  readonly sort_order?: number;
  readonly quality?: string;
}

/** MSTR-010 · The lead score's settings: every key the backend keeps, with its value. */
export const scoringResponseSchema = z
  .object({ data: z.array(z.object({ key: z.string().min(1), value: decimal })) })
  .transform(({ data }) => data.map((item) => ({ key: item.key, value: item.value })));

export type ScoringResponse = z.input<typeof scoringResponseSchema>;
export type ScoringItem = z.output<typeof scoringResponseSchema>[number];

/** PATCH /lookups/scoring: only the keys that change. Unknown keys are refused. */
export interface ScoringPatchRequest {
  readonly values: Readonly<Record<string, string>>;
}
