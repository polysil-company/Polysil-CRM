import { z } from "zod";

import { systemTypeSchema, type SystemType } from "./subsidy.schemas";

/**
 * SUBS-014 · Subsidy schemes, one per state (`backend/docs/api/subsidy-schemes.md`, handover
 * `subsidy-schemes-contract.md`): the list, a scheme's readiness — what each system still
 * lacks before it can calculate — its stages, and setting a new state's scheme up.
 */

const stateSchema = z.object({ id: z.string().min(1), code: z.string(), name: z.string() });

const schemeRowSchema = z
  .object({
    code: z.string().min(1),
    name: z.string(),
    is_active: z.boolean(),
    /** Null: the scheme isn't tied to a state yet. */
    state: stateSchema.nullable(),
    systems: z.array(systemTypeSchema),
    ready: z.boolean(),
    applications: z.number().int().nonnegative(),
  })
  .transform((wire) => ({
    code: wire.code,
    name: wire.name,
    active: wire.is_active,
    state: wire.state,
    systems: wire.systems,
    ready: wire.ready,
    applications: wire.applications,
  }));

export type SchemeRow = z.output<typeof schemeRowSchema>;
export type SchemeRowWire = z.input<typeof schemeRowSchema>;

export const schemeListSchema = z
  .object({ data: z.array(schemeRowSchema) })
  .transform(({ data }) => data);

const schemeDetailWireSchema = z.object({
  code: z.string().min(1),
  name: z.string(),
  is_active: z.boolean(),
  state: stateSchema.nullable(),
  /** The date readiness was checked for. */
  on: z.iso.date(),
  systems: z.array(
    z.object({
      system_type: systemTypeSchema,
      ready: z.boolean(),
      /** What a calculation would refuse on, in the order it would refuse. */
      missing: z.array(z.string()),
    }),
  ),
  stages: z.array(
    z.object({
      seq: z.number().int(),
      code: z.string().min(1),
      name: z.string(),
      is_active: z.boolean(),
    }),
  ),
  ready: z.boolean(),
});

export type SchemeDetailWire = z.input<typeof schemeDetailWireSchema>;

export const schemeDetailSchema = z
  .object({ data: schemeDetailWireSchema })
  .transform(({ data }) => ({
    code: data.code,
    name: data.name,
    active: data.is_active,
    state: data.state,
    on: data.on,
    systems: data.systems.map((system) => ({
      systemType: system.system_type,
      ready: system.ready,
      missing: system.missing,
    })),
    stages: data.stages.map((stage) => ({
      seq: stage.seq,
      code: stage.code,
      name: stage.name,
      active: stage.is_active,
    })),
    ready: data.ready,
  }));

export type SchemeDetail = z.output<typeof schemeDetailSchema>;

export const stageRenamedSchema = z.object({
  data: z.object({
    seq: z.number().int(),
    code: z.string(),
    name: z.string(),
    is_active: z.boolean(),
  }),
});

/** POST /subsidy-schemes */
export interface CreateSchemeRequest {
  /** 2 to 20 of A-Z, 0-9 and _; stored upper case. */
  readonly code: string;
  readonly name: string;
  readonly state_territory_id: string;
  /** The scheme whose engine settings and stages are copied; no figure is copied. */
  readonly template: string;
  /** A subset of the template's systems; null for all of them. */
  readonly systems: readonly SystemType[] | null;
}

/** PATCH /subsidy-schemes/{code} — any of these. */
export interface PatchSchemeRequest {
  readonly name?: string;
  readonly is_active?: boolean;
  /** Accepted only while the scheme has no state: how GGRC is linked to Gujarat. */
  readonly state_territory_id?: string;
}

/** The masters screen a `missing` item is filled on. */
export type MissingTable =
  "categories" | "parameters" | "component-rates" | "crop-spacings" | "unit-costs" | "quantities";
