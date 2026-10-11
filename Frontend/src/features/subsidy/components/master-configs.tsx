import type * as React from "react";

import {
  type MasterKind,
  type MasterRows,
  type RevisionRow,
  PARAMETER_UNITS,
} from "@/features/subsidy/api/subsidy-masters.schemas";
import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";
import type { EditableField } from "@/features/subsidy/lib/master-revision";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { EMPTY_VALUE, formatInr } from "@/lib/format";

/** SUBS-012 · How each master reads as a table, which figures may be revised, and how. */

export interface MasterColumn<TRow> {
  readonly key: string;
  readonly label: string;
  readonly numeric?: boolean;
  readonly cell: (row: TRow) => React.ReactNode;
}

/** Reads a revised field: the typed value, or null for an emptied optional one. */
export type FieldValue = (key: string) => string | null;

export interface MasterConfig<K extends MasterKind> {
  readonly kind: K;
  readonly label: string;
  readonly description: string;
  readonly columns: readonly MasterColumn<MasterRows[K][number]>[];
  /** The figures a revision may change; the key columns never change. */
  readonly fields: readonly EditableField[];
  /** What a row names itself by in a mistake, e.g. "Drip · small_farmer". */
  readonly rowName: (row: MasterRows[K][number]) => string;
  readonly toRevision: (row: MasterRows[K][number], value: FieldValue) => RevisionRow<K>;
  /** New rows a revision may add, when the table takes them. */
  readonly adding?: {
    readonly label: string;
    readonly fields: readonly EditableField[];
    readonly build: (value: FieldValue) => RevisionRow<K>;
  };
}

function system(value: SystemType | null): string {
  return value === null ? "Every system" : SYSTEM_LABELS[value];
}

const SYSTEM_OPTIONS = SYSTEM_TYPES.map((value) => ({ value, label: SYSTEM_LABELS[value] }));
const VARIANT_OPTIONS = [
  { value: "regular", label: "Regular" },
  { value: "seven_year", label: "Seven-year" },
] as const;
const UNIT_OPTIONS = PARAMETER_UNITS.map((value) => ({ value, label: value }));
const NOZZLE_OPTIONS = [
  { value: "plastic", label: "Plastic" },
  { value: "brass", label: "Brass" },
] as const;

/** A validated system field back as its type; the form allows only these values. */
function systemOf(value: string | null): SystemType {
  return SYSTEM_TYPES.find((item) => item === value) ?? "drip";
}

function systemOrNull(value: string | null): SystemType | null {
  return SYSTEM_TYPES.find((item) => item === value) ?? null;
}

export const CATEGORY_CONFIG: MasterConfig<"categories"> = {
  kind: "categories",
  label: "Categories",
  description:
    "Each system's farmer categories: the subsidy share, a cap per hectare, and GSDMA's share.",
  columns: [
    { key: "system", label: "System", cell: (row) => system(row.system_type) },
    {
      key: "name",
      label: "Category",
      cell: (row) => (
        <>
          {row.name}
          <span className="block text-xs text-muted-foreground">
            {row.code}
            {row.variant === "seven_year" ? " · 7-year" : ""}
          </span>
        </>
      ),
    },
    { key: "pct", label: "Share %", numeric: true, cell: (row) => row.pct },
    {
      key: "per_ha_cap",
      label: "Cap / Ha",
      numeric: true,
      cell: (row) => (row.per_ha_cap === null ? EMPTY_VALUE : formatInr(row.per_ha_cap)),
    },
    {
      key: "gsdma_pct",
      label: "GSDMA %",
      numeric: true,
      cell: (row) => row.gsdma_pct ?? EMPTY_VALUE,
    },
  ],
  fields: [
    { key: "name", label: "Name", required: true },
    { key: "pct", label: "Share %", places: 3, required: true, max: 100 },
    { key: "per_ha_cap", label: "Cap / Ha", places: 2, required: false },
    { key: "gsdma_pct", label: "GSDMA %", places: 3, required: false, max: 100 },
  ],
  rowName: (row) => `${system(row.system_type)} · ${row.name}`,
  toRevision: (row, value) => ({
    system_type: row.system_type,
    code: row.code,
    name: value("name") ?? row.name,
    pct: value("pct") ?? row.pct,
    variant: row.variant,
    per_ha_cap: value("per_ha_cap"),
    gsdma_pct: value("gsdma_pct"),
    sort_order: row.sort_order,
  }),
  adding: {
    label: "Add a category",
    fields: [
      { key: "system_type", label: "System", required: true, options: SYSTEM_OPTIONS },
      { key: "code", label: "Code", required: true },
      { key: "name", label: "Name", required: true },
      { key: "pct", label: "Share %", places: 3, required: true, max: 100 },
      { key: "variant", label: "Variant", required: true, options: VARIANT_OPTIONS },
      { key: "per_ha_cap", label: "Cap / Ha", places: 2, required: false },
      { key: "gsdma_pct", label: "GSDMA %", places: 3, required: false, max: 100 },
    ],
    build: (value) => ({
      system_type: systemOf(value("system_type")),
      code: value("code") ?? "",
      name: value("name") ?? "",
      pct: value("pct") ?? "0",
      variant: value("variant") === "seven_year" ? "seven_year" : "regular",
      per_ha_cap: value("per_ha_cap"),
      gsdma_pct: value("gsdma_pct"),
      sort_order: 0,
    }),
  },
};

export const PARAMETER_CONFIG: MasterConfig<"parameters"> = {
  kind: "parameters",
  label: "Parameters",
  description: "The constants behind the sums: rates, amounts and the seven-year window.",
  columns: [
    { key: "system", label: "System", cell: (row) => system(row.system_type) },
    {
      key: "key",
      label: "Parameter",
      cell: (row) => <span className="font-mono text-xs">{row.key}</span>,
    },
    { key: "value", label: "Value", numeric: true, cell: (row) => row.value },
    { key: "unit", label: "Unit", cell: (row) => row.unit },
  ],
  fields: [{ key: "value", label: "Value", places: 4, required: true }],
  rowName: (row) => `${system(row.system_type)} · ${row.key}`,
  toRevision: (row, value) => ({
    system_type: row.system_type,
    key: row.key,
    value: value("value") ?? row.value,
    unit: row.unit,
  }),
  adding: {
    label: "Add a parameter",
    fields: [
      { key: "system_type", label: "System", required: false, options: SYSTEM_OPTIONS },
      { key: "key", label: "Parameter", required: true },
      { key: "value", label: "Value", places: 4, required: true },
      { key: "unit", label: "Unit", required: true, options: UNIT_OPTIONS },
    ],
    build: (value) => ({
      system_type: systemOrNull(value("system_type")),
      key: value("key") ?? "",
      value: value("value") ?? "0",
      unit: value("unit") ?? "ratio",
    }),
  },
};

export const COMPONENT_RATE_CONFIG: MasterConfig<"component-rates"> = {
  kind: "component-rates",
  label: "Component rates",
  description: "The rates Sprinkler's derived items are priced at, by pipe size and nozzle.",
  columns: [
    { key: "system", label: "System", cell: (row) => system(row.system_type) },
    {
      key: "component",
      label: "Component",
      cell: (row) => (
        <>
          {row.description}
          <span className="block text-xs text-muted-foreground">
            {row.component_code}
            {row.pipe_size_mm === null ? "" : ` · ${String(row.pipe_size_mm)} mm`}
            {row.nozzle === null ? "" : ` · ${row.nozzle}`}
          </span>
        </>
      ),
    },
    { key: "uom", label: "Unit", cell: (row) => row.uom },
    {
      key: "rate",
      label: "Rate",
      numeric: true,
      cell: (row) => formatInr(row.rate, { paise: true }),
    },
  ],
  fields: [
    { key: "description", label: "Description", required: true },
    { key: "uom", label: "Unit", required: true },
    { key: "rate", label: "Rate", places: 2, required: true },
  ],
  rowName: (row) =>
    `${row.component_code}${row.pipe_size_mm === null ? "" : ` ${String(row.pipe_size_mm)} mm`}${row.nozzle === null ? "" : ` ${row.nozzle}`}`,
  toRevision: (row, value) => ({
    system_type: row.system_type,
    component_code: row.component_code,
    description: value("description") ?? row.description,
    uom: value("uom") ?? row.uom,
    pipe_size_mm: row.pipe_size_mm,
    nozzle: row.nozzle,
    rate: value("rate") ?? row.rate,
    source_cell: "admin",
  }),
  adding: {
    label: "Add a rate",
    fields: [
      { key: "system_type", label: "System", required: true, options: SYSTEM_OPTIONS },
      { key: "component_code", label: "Component code", required: true },
      { key: "description", label: "Description", required: true },
      { key: "uom", label: "Unit", required: true },
      { key: "pipe_size_mm", label: "Pipe (mm)", required: false, integer: true, max: 1000 },
      { key: "nozzle", label: "Nozzle", required: false, options: NOZZLE_OPTIONS },
      { key: "rate", label: "Rate", places: 2, required: true },
    ],
    build: (value) => {
      const pipe = value("pipe_size_mm");
      return {
        system_type: systemOf(value("system_type")),
        component_code: value("component_code") ?? "",
        description: value("description") ?? "",
        uom: value("uom") ?? "",
        pipe_size_mm: pipe === null ? null : Number(pipe),
        nozzle: value("nozzle"),
        rate: value("rate") ?? "0",
        source_cell: "admin",
      };
    },
  },
};

export const CROP_SPACING_CONFIG: MasterConfig<"crop-spacings"> = {
  kind: "crop-spacings",
  label: "Crop spacings",
  description:
    "Each crop's standard lateral spacing; the calculation uses the larger of this and the design's.",
  columns: [
    { key: "crop", label: "Crop", cell: (row) => row.crop },
    {
      key: "standard_spacing",
      label: "Standard spacing",
      numeric: true,
      cell: (row) => `${row.standard_spacing} m`,
    },
  ],
  fields: [{ key: "standard_spacing", label: "Standard spacing", places: 2, required: true }],
  rowName: (row) => row.crop,
  toRevision: (row, value) => ({
    crop: row.crop,
    standard_spacing: value("standard_spacing") ?? row.standard_spacing,
    sort_order: row.sort_order,
  }),
  adding: {
    label: "Add a crop",
    fields: [
      { key: "crop", label: "Crop", required: true },
      { key: "standard_spacing", label: "Standard spacing", places: 2, required: true },
    ],
    build: (value) => ({
      crop: value("crop") ?? "",
      standard_spacing: value("standard_spacing") ?? "0",
      sort_order: 0,
    }),
  },
};
