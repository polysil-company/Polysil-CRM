import { z } from "zod";

import {
  lookupItemWireSchema,
  toLookupItem,
  type LookupList,
} from "@/features/lookups/api/lookups.schemas";
import { cursorPageSchema } from "@/lib/api/pagination";

/**
 * MSTR-009, MSTR-010 · Writing the admin lists and the lead score's settings
 * (backend/docs/api/lookups.md). Rows are added and switched off, never renamed or deleted,
 * so a lead keeps the reason it was lost with (ADR-033).
 */

const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

/** One list row, as a write answers it. Reads come from MSTR-002's `lookupListResponseSchema`. */
export const lookupItemResponseSchema = z
  .object({ data: lookupItemWireSchema })
  .transform(({ data }) => toLookupItem(data));

export type LookupItemResponse = z.input<typeof lookupItemResponseSchema>;

/** BE-026 · The backend's bound on a sort order, either way. */
export const LOOKUP_SORT_ORDER_LIMIT = 1_000_000;

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

// ── MSTR-012 · territories ──────────────────────────────────────────────────────

/** State, then district, taluka and village: each sits under the level above. */
export const TERRITORY_LEVELS = ["state", "district", "taluka", "village"] as const;
export type TerritoryLevel = (typeof TERRITORY_LEVELS)[number];

/** One territory, as `/territories` answers it (backend/docs/api/territories.md). */
const territoryWireSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  level: z.enum(TERRITORY_LEVELS),
  /** A state's code numbers its leads (POL/<code>/<FY>/<n>); optional elsewhere. */
  code: z.string().nullable(),
  parent: z.object({ id: z.string().min(1), name: z.string(), level: z.string() }).nullable(),
  /** A lead is numbered under this state: its code can no longer change. */
  code_locked: z.boolean(),
  created_at: z.string().min(1),
});

export interface Territory {
  readonly id: string;
  readonly name: string;
  readonly level: TerritoryLevel;
  readonly code: string | null;
  readonly parent: { readonly id: string; readonly name: string; readonly level: string } | null;
  readonly codeLocked: boolean;
}

function toTerritory(wire: z.output<typeof territoryWireSchema>): Territory {
  return {
    id: wire.id,
    name: wire.name,
    level: wire.level,
    code: wire.code,
    parent: wire.parent,
    codeLocked: wire.code_locked,
  };
}

export const territoryListSchema = cursorPageSchema(territoryWireSchema.transform(toTerritory));

export const territoryResponseSchema = z
  .object({ data: territoryWireSchema })
  .transform(({ data }) => toTerritory(data));

export interface TerritoryListParams {
  /** Null: every level. */
  readonly level: TerritoryLevel | null;
  /** The children of this territory; null: anywhere. */
  readonly parentId: string | null;
  readonly q: string;
  readonly cursor: string | null;
}

/** POST /territories: a state at the root, or one level down under its parent. */
export interface TerritoryCreateRequest {
  readonly name: string;
  readonly level: TerritoryLevel;
  readonly parent_id: string | null;
  readonly code: string | null;
}

/** PATCH /territories/{id}: rename, or set the code (refused on a locked state). */
export interface TerritoryPatchRequest {
  readonly name?: string;
  readonly code?: string | null;
}
