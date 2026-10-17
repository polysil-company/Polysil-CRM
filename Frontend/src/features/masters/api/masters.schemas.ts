import { z } from "zod";

import type { LookupList } from "@/features/lookups/api/lookups.schemas";
import { cursorPageSchema } from "@/lib/api/pagination";

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

// ── MSTR-011 · offices ────────────────────────────────────────────────────────

const refSchema = z.object({ id: z.string().min(1), name: z.string() });

/** One office, as `/org-units` answers it (backend/docs/api/org-units.md, `OrgUnit`). */
export const officeWireSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  /** 1 (field) up to 5 (head office): the level of the role that runs it. */
  role_level: z.number().int(),
  parent: refSchema.nullable(),
  /** The territory a sales-line office covers; null for an HQ unit. */
  territory: refSchema.extend({ level: z.string().min(1) }).nullable(),
  is_open: z.boolean(),
  closed_at: z.string().nullable(),
  /** Active people anchored here. An office with any can't be closed. */
  active_users: z.number().int().nonnegative(),
  created_at: z.string().min(1),
});

type OfficeWire = z.output<typeof officeWireSchema>;

export interface Office {
  readonly id: string;
  readonly name: string;
  readonly roleLevel: number;
  readonly parent: OfficeWire["parent"];
  readonly territory: OfficeWire["territory"];
  readonly isOpen: boolean;
  readonly closedAt: OfficeWire["closed_at"];
  readonly activeUsers: number;
}

function toOffice(wire: OfficeWire): Office {
  return {
    id: wire.id,
    name: wire.name,
    roleLevel: wire.role_level,
    parent: wire.parent,
    territory: wire.territory,
    isOpen: wire.is_open,
    closedAt: wire.closed_at,
    activeUsers: wire.active_users,
  };
}

export const officeListSchema = cursorPageSchema(officeWireSchema.transform(toOffice));

export const officeResponseSchema = z
  .object({ data: officeWireSchema })
  .transform(({ data }) => toOffice(data));

/** Which offices the list shows. */
export const OFFICE_STATES = ["open", "closed", "all"] as const;
export type OfficeState = (typeof OFFICE_STATES)[number];

export interface OfficeListParams {
  readonly q: string;
  readonly state: OfficeState;
  readonly cursor: string | null;
}

/** POST /org-units. The name is unique among its siblings, case-insensitively. */
export interface OfficeCreateRequest {
  readonly name: string;
  readonly role_level: number;
  readonly parent_id: string | null;
  readonly territory_id: string | null;
}

/** PATCH /org-units/{id}: rename, move (`parent_id: null` makes a root), or re-cover. */
export interface OfficePatchRequest {
  readonly name?: string;
  readonly parent_id?: string | null;
  readonly territory_id?: string | null;
}
