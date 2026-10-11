"use client";

import { Add01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/features/session/hooks/use-session";
import { schemeListQueryOptions } from "@/features/subsidy/api/subsidy-schemes.queries";
import { todayInIndia } from "@/lib/format";

import {
  CATEGORY_CONFIG,
  COMPONENT_RATE_CONFIG,
  CROP_SPACING_CONFIG,
  PARAMETER_CONFIG,
} from "./master-configs";
import { MasterPanel } from "./master-panel";
import { MatrixPanel } from "./matrix-panel";
import { NewSchemeForm, SchemeOverview } from "./scheme-overview";

const TABLES = [
  "overview",
  "categories",
  "parameters",
  "component-rates",
  "crop-spacings",
  "unit-costs",
  "quantities",
] as const;
type Table = (typeof TABLES)[number];

const TABLE_LABELS: Readonly<Record<Table, string>> = {
  overview: "Overview",
  categories: "Categories",
  parameters: "Parameters",
  "component-rates": "Component rates",
  "crop-spacings": "Crop spacings",
  "unit-costs": "Unit costs",
  quantities: "Quantities",
};

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The scheme the screen opens on: Gujarat's, the one every state had before 044. */
const DEFAULT_SCHEME = "GGRC";

/**
 * SUBS-012, SUBS-013, SUBS-014 · The subsidy masters behind every calculation, one state's
 * scheme at a time, as in force on a date (today by default, or any other to see what applied
 * then). Whoever may edit masters revises a table's rows, or starts a new matrix, from today or
 * a later date; nothing is overwritten. The overview says what a scheme still lacks, and a new
 * state's scheme is set up from it.
 */
export function SubsidyMasters(): React.JSX.Element {
  const canEdit = useCan("masters", "edit");
  const [values, setValues] = useQueryStates({
    table: parseAsStringLiteral(TABLES).withDefault("overview"),
    scheme: parseAsString.withDefault(DEFAULT_SCHEME),
    on: parseAsString,
  });
  const [creating, setCreating] = useState(false);
  const schemes = useQuery(schemeListQueryOptions());
  const on = values.on !== null && DATE.test(values.on) ? values.on : null;
  const today = todayInIndia();
  const scheme = values.scheme;
  const rows = schemes.data ?? [];
  const row = rows.find((item) => item.code === scheme) ?? null;
  const unlinked = rows.find((item) => item.state === null) ?? null;
  // The URL may name a scheme the list doesn't have yet (or any more); keep it selectable.
  const choices =
    row === null ? [{ value: scheme, label: scheme }, ...rows.map(toItem)] : rows.map(toItem);

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        The figures every subsidy calculation reads, for each state&apos;s scheme. A revision starts
        today or later, so applications already started keep the figures they were calculated with.
        {canEdit ? "" : " Only administrators of masters can revise them."}
      </p>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <Field className="sm:w-64">
          <FieldLabel htmlFor="masters-scheme">Scheme</FieldLabel>
          <Select
            items={choices}
            value={scheme}
            onValueChange={(next) => {
              if (typeof next !== "string") return;
              void setValues({ scheme: next === DEFAULT_SCHEME ? null : next });
            }}
          >
            <SelectTrigger
              id="masters-scheme"
              className="w-full"
              aria-describedby="masters-scheme-hint"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {choices.map((choice) => (
                <SelectItem key={choice.value} value={choice.value}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldDescription id="masters-scheme-hint">
            {schemes.isError
              ? "The list of schemes didn't load; showing the one asked for."
              : row === null
                ? "Loading the schemes…"
                : `${row.state?.name ?? "No state yet"}${row.active ? "" : " · switched off"}`}
          </FieldDescription>
        </Field>
        <Field className="sm:w-56">
          <FieldLabel htmlFor="masters-on">In force on</FieldLabel>
          <div className="flex items-center gap-2">
            <Input
              id="masters-on"
              type="date"
              value={on ?? today}
              aria-describedby="masters-on-hint"
              onChange={(event) => {
                const next = event.target.value;
                void setValues({ on: next === "" || next === today ? null : next });
              }}
            />
            {on === null ? null : (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  void setValues({ on: null });
                }}
              >
                Today
              </Button>
            )}
          </div>
          <FieldDescription id="masters-on-hint">
            {on === null ? "Today's figures." : "Earlier or later figures, as they apply that day."}
          </FieldDescription>
        </Field>
        {canEdit ? (
          <Button
            variant="outline"
            className="sm:mb-6 sm:ml-auto"
            disabled={unlinked !== null || schemes.data === undefined}
            onClick={() => {
              setCreating(true);
            }}
          >
            <Icon icon={Add01Icon} />
            New scheme
          </Button>
        ) : null}
      </div>

      <Tabs
        value={values.table}
        onValueChange={(table: Table) => {
          void setValues({ table: table === "overview" ? null : table });
        }}
      >
        <TabsList aria-label="Subsidy master" className="scrollbar-none overflow-x-auto">
          {TABLES.map((table) => (
            <TabsTrigger key={table} value={table}>
              {TABLE_LABELS[table]}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview">
          <SchemeOverview
            scheme={scheme}
            row={row}
            unlinked={unlinked}
            on={on}
            canEdit={canEdit}
            onOpenTable={(table) => {
              void setValues({ table });
            }}
          />
        </TabsContent>
        <TabsContent value="categories">
          <MasterPanel config={CATEGORY_CONFIG} scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="parameters">
          <MasterPanel config={PARAMETER_CONFIG} scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="component-rates">
          <MasterPanel config={COMPONENT_RATE_CONFIG} scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="crop-spacings">
          <MasterPanel config={CROP_SPACING_CONFIG} scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="unit-costs">
          <MatrixPanel kind="unit-cost" scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="quantities">
          <MatrixPanel kind="quantity" scheme={scheme} on={on} canEdit={canEdit} />
        </TabsContent>
      </Tabs>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          {creating ? (
            <NewSchemeForm
              schemes={rows}
              onCreated={(code) => {
                setCreating(false);
                void setValues({ scheme: code, table: null });
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function toItem(row: { code: string; name: string }): { value: string; label: string } {
  return { value: row.code, label: `${row.code} · ${row.name}` };
}
