import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  MASTER_KINDS,
  PARAMETER_UNITS,
  type MasterKind,
  type MasterRows,
} from "@/features/subsidy/api/subsidy-masters.schemas";
import { systemTypeSchema } from "@/features/subsidy/api/subsidy.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import type { MockSubsidyMasters } from "@/mocks/data/subsidy-masters";
import { MOCK_DEFAULT_SCHEME } from "@/mocks/data/subsidy-schemes";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * SUBS-012, SUBS-013 · The subsidy masters, with the backend's revision rules: a revision
 * starts today or later; each row closes the row with its key in force that day and starts
 * from it; a row whose key already starts that day or later is refused (409). A new matrix
 * ends the one in force for its system (and variant). Each scheme has its own (SUBS-014).
 */

const decimal = (places: number): z.ZodType<string> =>
  z
    .string()
    .regex(/^\d+(\.\d+)?$/)
    .refine((value) => (value.split(".")[1]?.length ?? 0) <= places, {
      message: `at most ${String(places)} decimals`,
    });

const ROW_SCHEMAS = {
  categories: z.object({
    system_type: systemTypeSchema,
    code: z.string().min(1).max(60),
    name: z.string().min(1).max(200),
    pct: decimal(3).refine((value) => Number(value) > 0 && Number(value) <= 100, "0 to 100"),
    variant: z.enum(["regular", "seven_year"]),
    per_ha_cap: decimal(2).nullable().default(null),
    gsdma_pct: decimal(3).nullable().default(null),
    sort_order: z.number().int().default(0),
  }),
  parameters: z.object({
    system_type: systemTypeSchema.nullable().default(null),
    key: z.string().min(1).max(80),
    value: decimal(4),
    unit: z.enum(PARAMETER_UNITS),
  }),
  "component-rates": z.object({
    system_type: systemTypeSchema,
    component_code: z.string().min(1).max(60),
    description: z.string().min(1).max(300),
    uom: z.string().min(1).max(20),
    pipe_size_mm: z.number().int().positive().nullable().default(null),
    nozzle: z.string().max(40).nullable().default(null),
    rate: decimal(2),
    source_cell: z.string().min(1).max(60).default("admin"),
  }),
  "crop-spacings": z.object({
    crop: z.string().min(1).max(100),
    standard_spacing: decimal(2),
    sort_order: z.number().int().default(0),
  }),
} as const satisfies Record<MasterKind, z.ZodType>;

/** The fields that make a row the same row across revisions. */
const KEYS: Readonly<Record<MasterKind, readonly string[]>> = {
  categories: ["system_type", "code"],
  parameters: ["system_type", "key"],
  "component-rates": ["system_type", "component_code", "pipe_size_mm", "nozzle"],
  "crop-spacings": ["crop"],
};

const revisionSchema = z.object({
  scheme: z.string().default("GGRC"),
  effective_from: z.iso.date(),
  rows: z.array(z.record(z.string(), z.unknown())).min(1).max(2000),
});

const unitCostCell = z.object({
  lateral_spacing: decimal(2).nullable().default(null),
  area_breakpoint: decimal(3),
  unit_cost: decimal(4),
});
const quantityCell = z.object({
  component_code: z.string().min(1).max(60),
  area_breakpoint: decimal(3),
  qty: decimal(2),
});
const matrixSchema = z.object({
  scheme: z.string().default("GGRC"),
  system_type: systemTypeSchema,
  variant: z.enum(["regular", "seven_year"]).nullable().default(null),
  dimensionality: z
    .union([z.literal(1), z.literal(2)])
    .nullable()
    .default(null),
  effective_from: z.iso.date(),
  source: z.string().min(1).max(200),
  unit_cost_cells: z.array(unitCostCell).max(5000).nullable().default(null),
  quantity_cells: z.array(quantityCell).max(5000).nullable().default(null),
});

function inForce(
  row: { effective_from: string; effective_to: string | null },
  on: string,
): boolean {
  return row.effective_from <= on && (row.effective_to === null || row.effective_to > on);
}

function mayEdit(): boolean {
  return can(mockPermissionsFor(readMockRole()), "masters", "edit");
}

function sameKey(
  kind: MasterKind,
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): boolean {
  return KEYS[kind].every((key) => {
    const left = a[key] ?? null;
    const right = b[key] ?? null;
    return typeof left === "string" && typeof right === "string"
      ? left.toLowerCase() === right.toLowerCase()
      : left === right;
  });
}

function newId(): string {
  let count = 0;
  for (const masters of mockDb.subsidyMasters.values()) {
    count +=
      MASTER_KINDS.reduce((sum, kind) => sum + masters[kind].length, 0) +
      masters.unitCostMatrices.length +
      masters.quantityMatrices.length;
  }
  return mockUuid(MOCK_ID_SPACE.subsidyMaster, 0x10000 + count);
}

/** The masters of the scheme a request names (GGRC when it names none). */
function mastersOf(scheme: string | null | undefined): MockSubsidyMasters | null {
  return mockDb.subsidyMasters.get((scheme ?? MOCK_DEFAULT_SCHEME).toUpperCase()) ?? null;
}

function noScheme(): Response {
  return errorResponse(404, "not_found", "No such scheme.");
}

function readKind(value: unknown): MasterKind | null {
  return MASTER_KINDS.find((kind) => kind === value) ?? null;
}

function pastDate(): Response {
  return errorResponse(
    422,
    "revision_in_past",
    "A revision starts today or later; a backdated one would restate stored calculations.",
    { effective_from: "Today or later." },
  );
}

/** Revises one kind's rows; the generic keeps each kind's row shape. */
function revise<K extends MasterKind>(
  masters: MockSubsidyMasters,
  kind: K,
  effectiveFrom: string,
  rows: readonly MasterRows[K][number][],
): Response | { closed: number; inserted: number } {
  const table: MasterRows[K][number][] = masters[kind];
  for (const [index, row] of rows.entries()) {
    const later = table.find(
      (existing) => sameKey(kind, existing, row) && existing.effective_from >= effectiveFrom,
    );
    if (later !== undefined) {
      const onDay = later.effective_from === effectiveFrom;
      return errorResponse(
        409,
        onDay ? "revision_on_start_date" : "later_revision_exists",
        onDay
          ? "A row with this key already starts on that date."
          : "A later revision exists for this row; revise from after it.",
        {
          [`rows[${String(index)}]`]: onDay
            ? "Starts that day already."
            : "A later revision exists.",
        },
      );
    }
  }
  let closed = 0;
  for (const row of rows) {
    for (const existing of table) {
      if (sameKey(kind, existing, row) && inForce(existing, effectiveFrom)) {
        existing.effective_to = effectiveFrom;
        closed += 1;
      }
    }
    table.push({ ...row, effective_from: effectiveFrom, effective_to: null });
  }
  return { closed, inserted: rows.length };
}

export const subsidyMasterHandlers = [
  http.get(buildApiUrl("/subsidy-masters/:kind/matrices"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const url = new URL(request.url);
    const on = url.searchParams.get("on") ?? todayInIndia();
    const masters = mastersOf(url.searchParams.get("scheme"));
    if (masters === null) return noScheme();
    if (params.kind === "unit-cost-matrices") {
      return HttpResponse.json({
        data: masters.unitCostMatrices.filter((matrix) => inForce(matrix, on)),
      });
    }
    if (params.kind === "quantity-matrices") {
      return HttpResponse.json({
        data: masters.quantityMatrices.filter((matrix) => inForce(matrix, on)),
      });
    }
    return errorResponse(404, "not_found", "No such matrix kind.");
  }),

  http.post(buildApiUrl("/subsidy-masters/:kind/matrices"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Not permitted.");
    const parsed = matrixSchema.safeParse(await request.json());
    if (!parsed.success) {
      const fields: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fields[issue.path.map(String).join(".")] = issue.message;
      }
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const body = parsed.data;
    if (body.effective_from < todayInIndia()) return pastDate();
    const masters = mastersOf(body.scheme);
    if (masters === null) return noScheme();
    if (params.kind === "unit-cost-matrices") {
      if (body.unit_cost_cells === null || body.variant === null || body.dimensionality === null) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          unit_cost_cells: "Cells, variant and dimensionality are required.",
        });
      }
      const same = masters.unitCostMatrices.filter(
        (matrix) => matrix.system_type === body.system_type && matrix.variant === body.variant,
      );
      const later = same.find((matrix) => matrix.effective_from >= body.effective_from);
      if (later !== undefined) {
        return errorResponse(
          409,
          later.effective_from === body.effective_from
            ? "revision_on_start_date"
            : "later_revision_exists",
          "A matrix already starts on or after that date.",
        );
      }
      const current = same.filter((matrix) => inForce(matrix, body.effective_from));
      for (const matrix of current) matrix.effective_to = body.effective_from;
      masters.unitCostMatrices.push({
        id: newId(),
        system_type: body.system_type,
        variant: body.variant,
        dimensionality: body.dimensionality,
        effective_from: body.effective_from,
        effective_to: null,
        source: body.source,
        cells: body.unit_cost_cells,
      });
      return HttpResponse.json(
        {
          data: {
            closed: current.length,
            inserted: body.unit_cost_cells.length,
            effective_from: body.effective_from,
          },
        },
        { status: 201 },
      );
    }
    if (params.kind === "quantity-matrices") {
      if (body.quantity_cells === null) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          quantity_cells: "Cells are required.",
        });
      }
      const same = masters.quantityMatrices.filter(
        (matrix) => matrix.system_type === body.system_type,
      );
      const later = same.find((matrix) => matrix.effective_from >= body.effective_from);
      if (later !== undefined) {
        return errorResponse(
          409,
          later.effective_from === body.effective_from
            ? "revision_on_start_date"
            : "later_revision_exists",
          "A matrix already starts on or after that date.",
        );
      }
      const current = same.filter((matrix) => inForce(matrix, body.effective_from));
      for (const matrix of current) matrix.effective_to = body.effective_from;
      masters.quantityMatrices.push({
        id: newId(),
        system_type: body.system_type,
        effective_from: body.effective_from,
        effective_to: null,
        source: body.source,
        cells: body.quantity_cells,
      });
      return HttpResponse.json(
        {
          data: {
            closed: current.length,
            inserted: body.quantity_cells.length,
            effective_from: body.effective_from,
          },
        },
        { status: 201 },
      );
    }
    return errorResponse(404, "not_found", "No such matrix kind.");
  }),

  http.get(buildApiUrl("/subsidy-masters/:kind"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const kind = readKind(params.kind);
    if (kind === null) return errorResponse(404, "not_found", "No such master.");
    const url = new URL(request.url);
    const on = url.searchParams.get("on") ?? todayInIndia();
    const masters = mastersOf(url.searchParams.get("scheme"));
    if (masters === null) return noScheme();
    const rows: Record<string, unknown>[] = masters[kind].filter((row) => inForce(row, on));
    return HttpResponse.json({ data: rows });
  }),

  http.post(buildApiUrl("/subsidy-masters/:kind/revisions"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Not permitted.");
    const kind = readKind(params.kind);
    if (kind === null) return errorResponse(404, "not_found", "No such master.");
    const parsed = revisionSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        rows: "1 to 2000 rows",
      });
    }
    const { effective_from: effectiveFrom, rows: raw } = parsed.data;
    if (effectiveFrom < todayInIndia()) return pastDate();
    const masters = mastersOf(parsed.data.scheme);
    if (masters === null) return noScheme();
    const schema = ROW_SCHEMAS[kind];
    const fields: Record<string, string> = {};
    const rows = raw.flatMap((row, index) => {
      const checked = schema.safeParse(row);
      if (!checked.success) {
        fields[`rows[${String(index)}]`] = checked.error.issues[0]?.message ?? "invalid";
        return [];
      }
      return [{ ...checked.data, id: newId() }];
    });
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const result = (() => {
      switch (kind) {
        case "categories":
          return revise(
            masters,
            "categories",
            effectiveFrom,
            rows.flatMap((row) =>
              "code" in row ? [{ ...row, effective_from: effectiveFrom, effective_to: null }] : [],
            ),
          );
        case "parameters":
          return revise(
            masters,
            "parameters",
            effectiveFrom,
            rows.flatMap((row) =>
              "key" in row ? [{ ...row, effective_from: effectiveFrom, effective_to: null }] : [],
            ),
          );
        case "component-rates":
          return revise(
            masters,
            "component-rates",
            effectiveFrom,
            rows.flatMap((row) =>
              "component_code" in row
                ? [{ ...row, effective_from: effectiveFrom, effective_to: null }]
                : [],
            ),
          );
        case "crop-spacings":
          return revise(
            masters,
            "crop-spacings",
            effectiveFrom,
            rows.flatMap((row) =>
              "crop" in row && "standard_spacing" in row
                ? [{ ...row, effective_from: effectiveFrom, effective_to: null }]
                : [],
            ),
          );
      }
    })();
    if (result instanceof Response) return result;
    return HttpResponse.json(
      { data: { ...result, effective_from: effectiveFrom } },
      { status: 201 },
    );
  }),
];
