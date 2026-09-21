import { z } from "zod";

/**
 * MSTR-002 · The lists behind the lead screens' pickers, from the backend's `GET /lookups/*`
 * endpoints (backend/docs/api/lookups.md, `LookupItem` and `TerritoryPick` in its OpenAPI).
 *
 * Administrators edit these lists, so screens never hard-code their codes or names: a lead
 * carries a code (`source: "agri_fair"`) and the name comes from here.
 */

/** The editable lists the lead screens read, by their path under /lookups. */
export const LOOKUP_LISTS = ["lead-sources", "mis-systems", "lost-reasons"] as const;
export type LookupList = (typeof LOOKUP_LISTS)[number];

const lookupItemWireSchema = z.object({
  id: z.string().min(1),
  code: z.string().min(1),
  name: z.string().min(1),
  /** Inactive rows are kept so old records still show a name; new records cannot use them. */
  is_active: z.boolean().optional(),
});

export const lookupListResponseSchema = z
  .object({ data: z.array(lookupItemWireSchema) })
  .transform(({ data }) =>
    data.map((item) => ({
      id: item.id,
      code: item.code,
      name: item.name,
      isActive: item.is_active ?? true,
    })),
  );

/** The backend's JSON, as the mock backend must produce it. */
export type LookupListWire = z.input<typeof lookupListResponseSchema>;
export type LookupItem = z.output<typeof lookupListResponseSchema>[number];

const territoryRefSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  /** state, district, taluka or village. */
  level: z.string().min(1),
});

export const territoryListResponseSchema = z
  .object({
    data: z.array(
      territoryRefSchema.extend({
        code: z.string().nullish(),
        parent: territoryRefSchema.nullish(),
      }),
    ),
  })
  .transform(({ data }) =>
    data.map((territory) => ({
      id: territory.id,
      name: territory.name,
      level: territory.level,
      code: territory.code ?? null,
      parent: territory.parent ?? null,
    })),
  );

export type TerritoryListWire = z.input<typeof territoryListResponseSchema>;
export type TerritoryWire = TerritoryListWire["data"][number];
export type TerritoryOption = z.output<typeof territoryListResponseSchema>[number];

/** A territory as a form keeps it: enough to send its id and to name it in the field. */
export interface TerritoryChoice {
  readonly id: string;
  readonly name: string;
  readonly level: string;
  readonly parent?: { readonly name: string } | null | undefined;
}

/**
 * GET /lookups/territories filters. With no search the picker lists districts to start
 * from; a search matches names at every level.
 */
export interface TerritorySearchParams {
  readonly q: string;
  readonly level: string | null;
  readonly limit: number;
}
