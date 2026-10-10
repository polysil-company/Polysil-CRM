"use client";

import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TextField } from "@/features/quotations/components/builder-parts";
import {
  NOZZLES,
  type Nozzle,
  type SubsidyCrop,
  type SystemConfig,
} from "@/features/subsidy/api/subsidy.schemas";
import {
  emptyLine,
  isBlankLine,
  linePaths,
  type CalculatorDraft,
  type DraftCrop,
  type DraftLine,
  type DraftProblems,
} from "@/features/subsidy/lib/calculator-draft";
import { cn } from "@/lib/utils";

import { CropPicker } from "./crop-picker";

const NOZZLE_LABELS: Readonly<Record<Nozzle, string>> = { plastic: "Plastic", brass: "Brass" };

const LINE_FIELDS = ["description", "uom", "rate", "qty"] as const;
type LineField = (typeof LINE_FIELDS)[number];

const LINE_FIELD_LABELS: Readonly<Record<LineField, string>> = {
  description: "Item",
  uom: "Unit",
  rate: "Rate",
  qty: "Quantity",
};

/** The first problem among a group of field paths, for a message under the group. */
function firstProblem(problems: DraftProblems, paths: readonly string[]): string | undefined {
  for (const path of paths) {
    const problem = problems[path];
    if (problem !== undefined) return problem;
  }
  return undefined;
}

// ── lines ─────────────────────────────────────────────────────────────────────────

export interface LinesEditorProps {
  /** e.g. "crop-0-lines" — unique on the page. */
  idPrefix: string;
  /** The backend's path for these rows, e.g. "crops[0].lines" or "head_lines". */
  basePath: string;
  /** "Field unit item" — names each row for assistive technology. */
  rowName: string;
  lines: readonly DraftLine[];
  problems: DraftProblems;
  onChange: (lines: readonly DraftLine[]) => void;
}

/**
 * SUBS-002 · Bill-of-quantities rows as the designer types them: item, unit, rate, quantity.
 * A row left blank is not sent. The rate is the scheme's, not our price list's (GAP-080).
 */
export function LinesEditor({
  idPrefix,
  basePath,
  rowName,
  lines,
  problems,
  onChange,
}: LinesEditorProps): React.JSX.Element {
  const paths = linePaths(lines, basePath);
  const change = (next: DraftLine): void => {
    onChange(lines.map((line) => (line.key === next.key ? next : line)));
  };

  return (
    <div className="flex flex-col gap-2">
      <div
        aria-hidden
        className="hidden grid-cols-12 gap-2 px-1 text-xs text-muted-foreground md:grid"
      >
        <span className="col-span-5">Item</span>
        <span className="col-span-2">Unit</span>
        <span className="col-span-2">Rate (₹)</span>
        <span className="col-span-2">Quantity</span>
      </div>
      <ul aria-label={`${rowName}s`} className="flex flex-col gap-2">
        {lines.map((line, index) => {
          const number = index + 1;
          const path = paths[line.key];
          const message =
            path === undefined
              ? undefined
              : firstProblem(
                  problems,
                  LINE_FIELDS.map((field) => `${path}.${field}`),
                );
          const messageId = `${idPrefix}-${line.key}-message`;
          return (
            <li
              key={line.key}
              aria-label={`${rowName} ${String(number)}`}
              className={cn(
                "grid grid-cols-12 gap-2 rounded-lg border border-border p-2 md:border-0 md:p-0",
                message !== undefined && "border-danger",
              )}
            >
              {LINE_FIELDS.map((field) => {
                const id = `${idPrefix}-${line.key}-${field}`;
                const invalid = path !== undefined && problems[`${path}.${field}`] !== undefined;
                const numeric = field === "rate" || field === "qty";
                return (
                  <div
                    key={field}
                    className={cn(
                      "flex min-w-0 flex-col gap-1",
                      field === "description" && "col-span-10 md:col-span-5",
                      field === "uom" && "col-span-3 md:col-span-2",
                      field === "rate" && "col-span-5 md:col-span-2",
                      field === "qty" && "col-span-4 md:col-span-2",
                    )}
                  >
                    <label htmlFor={id} className="text-xs text-muted-foreground md:sr-only">
                      {LINE_FIELD_LABELS[field]}
                      <span className="sr-only">
                        {" "}
                        of {rowName.toLowerCase()} {number}
                      </span>
                    </label>
                    <Input
                      id={id}
                      value={line[field]}
                      inputMode={numeric ? "decimal" : undefined}
                      autoComplete="off"
                      placeholder={field === "uom" ? "Mtr." : undefined}
                      className={numeric ? "tabular-nums" : undefined}
                      aria-invalid={invalid || undefined}
                      aria-describedby={message === undefined ? undefined : messageId}
                      onChange={(event) => {
                        change({ ...line, [field]: event.target.value });
                      }}
                    />
                  </div>
                );
              })}
              <div className="col-span-2 row-start-1 flex items-end justify-end md:col-span-1 md:col-start-12 md:items-center">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-md"
                  aria-label={`Remove ${rowName.toLowerCase()} ${String(number)}`}
                  disabled={lines.length === 1 && isBlankLine(line)}
                  onClick={() => {
                    const rest = lines.filter((item) => item.key !== line.key);
                    onChange(rest.length === 0 ? [emptyLine()] : rest);
                  }}
                >
                  <Icon icon={Delete02Icon} />
                </Button>
              </div>
              {message === undefined ? null : (
                <p id={messageId} className="col-span-12 text-xs text-danger">
                  {message}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => {
          onChange([...lines, emptyLine()]);
        }}
      >
        <Icon icon={Add01Icon} />
        Add {rowName.toLowerCase()}
      </Button>
    </div>
  );
}

// ── a crop block ──────────────────────────────────────────────────────────────────

export interface CropBlockCardProps {
  crop: DraftCrop;
  index: number;
  system: SystemConfig;
  catalogue: readonly SubsidyCrop[];
  problems: DraftProblems;
  onChange: (next: DraftCrop) => void;
  /** Absent for the first block, which always stays. */
  onRemove?: (() => void) | undefined;
}

function standardOf(catalogue: readonly SubsidyCrop[], name: string | null): string | null {
  if (name === null) return null;
  return catalogue.find((row) => row.crop === name)?.standardSpacing ?? null;
}

/**
 * SUBS-002 · One crop block: what grows, on how much land, at what spacing, and its field-unit
 * lines. The inter-crop, when there is one, sets the standard spacing — not the main crop.
 */
export function CropBlockCard({
  crop,
  index,
  system,
  catalogue,
  problems,
  onChange,
  onRemove,
}: CropBlockCardProps): React.JSX.Element {
  const at = `crops[${String(index)}]`;
  const id = `crop-${String(index)}`;
  const isSprinkler = system.systemType === "sprinkler";
  const standard = standardOf(catalogue, crop.interCrop ?? crop.crop);
  const setter =
    <TKey extends keyof DraftCrop>(key: TKey) =>
    (value: DraftCrop[TKey]): void => {
      onChange({ ...crop, [key]: value });
    };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>
            {system.cropCountMax > 1 ? `Crop block ${String(index + 1)}` : "Crop"}
          </CardTitle>
          <CardDescription>
            {isSprinkler
              ? "The engine derives the pipes, couplers and nozzles from the area."
              : "Its own area, spacing and field-unit items."}
          </CardDescription>
        </div>
        {onRemove === undefined ? null : (
          <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
            <Icon icon={Delete02Icon} />
            Remove
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={`${id}-crop`}
            label="Crop"
            optional
            error={problems[`${at}.crop`]}
            description={
              crop.crop === null
                ? "No crop means a standard spacing of 0."
                : `Standard spacing ${standardOf(catalogue, crop.crop) ?? "—"} m.`
            }
          >
            {(aria) => (
              <CropPicker
                {...aria}
                crops={catalogue}
                value={crop.crop}
                onValueChange={setter("crop")}
                placeholder="Search crops"
              />
            )}
          </TextField>
          <TextField
            id={`${id}-inter-crop`}
            label="Inter-crop"
            optional
            error={problems[`${at}.inter_crop`]}
            description={
              crop.interCrop === null
                ? "A second crop in the same block sets the standard spacing."
                : `Standard spacing ${standardOf(catalogue, crop.interCrop) ?? "—"} m — this one counts.`
            }
          >
            {(aria) => (
              <CropPicker
                {...aria}
                crops={catalogue}
                value={crop.interCrop}
                onValueChange={setter("interCrop")}
                placeholder="None"
              />
            )}
          </TextField>

          {isSprinkler ? (
            <TextField
              id={`${id}-area`}
              label="Area"
              error={problems[`${at}.area`]}
              description="The scheme's table holds only these areas."
            >
              {(aria) => (
                <Select
                  items={(system.sprinklerAreas ?? []).map((area) => ({
                    value: area,
                    label: `${area} Ha`,
                  }))}
                  value={crop.area === "" ? null : crop.area}
                  onValueChange={(value) => {
                    if (typeof value === "string") setter("area")(value);
                  }}
                >
                  <SelectTrigger {...aria} className="w-full">
                    <SelectValue placeholder="Choose the area" />
                  </SelectTrigger>
                  <SelectContent>
                    {(system.sprinklerAreas ?? []).map((area) => (
                      <SelectItem key={area} value={area}>
                        {area} Ha
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </TextField>
          ) : (
            <TextField
              id={`${id}-area`}
              label="Area"
              error={problems[`${at}.area`]}
              description="In hectares, up to three decimals."
            >
              {(aria) => (
                <InputGroup>
                  <InputGroupInput
                    {...aria}
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="1.000"
                    className="tabular-nums"
                    value={crop.area}
                    onChange={(event) => {
                      setter("area")(event.target.value);
                    }}
                  />
                  <InputGroupAddon align="end">Ha</InputGroupAddon>
                </InputGroup>
              )}
            </TextField>
          )}

          <TextField
            id={`${id}-lateral`}
            label="Lateral spacing"
            error={problems[`${at}.lateral_spacing`]}
            description={
              standard === null
                ? "As designed, in metres."
                : `As designed. The subsidy uses the larger of this and ${standard} m.`
            }
          >
            {(aria) => (
              <InputGroup>
                <InputGroupInput
                  {...aria}
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="1.20"
                  className="tabular-nums"
                  value={crop.lateralSpacing}
                  onChange={(event) => {
                    setter("lateralSpacing")(event.target.value);
                  }}
                />
                <InputGroupAddon align="end">m</InputGroupAddon>
              </InputGroup>
            )}
          </TextField>

          <TextField
            id={`${id}-crop-spacing`}
            label="Crop spacing"
            optional
            error={problems[`${at}.crop_spacing`]}
            description="As it prints on the quotation, e.g. 1.37 x 0.50."
            className="sm:col-span-2"
          >
            {(aria) => (
              <Input
                {...aria}
                autoComplete="off"
                maxLength={60}
                value={crop.cropSpacing}
                onChange={(event) => {
                  setter("cropSpacing")(event.target.value);
                }}
              />
            )}
          </TextField>
        </FieldGroup>

        {isSprinkler ? null : (
          <div role="group" aria-labelledby={`${id}-lines-title`} className="flex flex-col gap-2">
            <h3 id={`${id}-lines-title`} className="text-sm font-medium text-foreground">
              Field unit
            </h3>
            <LinesEditor
              idPrefix={`${id}-lines`}
              basePath={`${at}.lines`}
              rowName="Field unit item"
              lines={crop.lines}
              problems={problems}
              onChange={setter("lines")}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── the head unit and the costs ─────────────────────────────────────────────────

export interface QuotationCostsCardProps {
  draft: CalculatorDraft;
  system: SystemConfig;
  problems: DraftProblems;
  onChange: (next: CalculatorDraft) => void;
}

/** SUBS-002 · The head unit, shared across crops by area. Drip and Mini Sprinkler only. */
export function HeadUnitCard({
  draft,
  problems,
  onChange,
}: Omit<QuotationCostsCardProps, "system">): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Head unit</CardTitle>
          <CardDescription>
            The pump-end equipment, sent once and shared across the crops by area.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <LinesEditor
          idPrefix="head-lines"
          basePath="head_lines"
          rowName="Head unit item"
          lines={draft.headLines}
          problems={problems}
          onChange={(headLines) => {
            onChange({ ...draft, headLines });
          }}
        />
      </CardContent>
    </Card>
  );
}

/** SUBS-002 · Installation, the sump, a shared water source, and Sprinkler's nozzle. */
export function QuotationCostsCard({
  draft,
  system,
  problems,
  onChange,
}: QuotationCostsCardProps): React.JSX.Element {
  const isSprinkler = system.systemType === "sprinkler";
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Installation and extras</CardTitle>
          <CardDescription>Rates per hectare; the quantity is the area.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <TextField
            id="installation-rate"
            label="Installation rate"
            optional
            error={problems.installation_rate_per_ha}
            description="Per hectare."
          >
            {(aria) => (
              <InputGroup>
                <InputGroupAddon>₹</InputGroupAddon>
                <InputGroupInput
                  {...aria}
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="0"
                  className="tabular-nums"
                  value={draft.installationRate}
                  onChange={(event) => {
                    onChange({ ...draft, installationRate: event.target.value });
                  }}
                />
                <InputGroupAddon align="end">/ Ha</InputGroupAddon>
              </InputGroup>
            )}
          </TextField>

          {isSprinkler ? null : (
            <TextField
              id="sump-rate"
              label="Sump rate"
              optional
              error={problems["sump.rate_per_ha"]}
              description="The farmer's own cost. Raises the allowed cost, not the subsidy share."
            >
              {(aria) => (
                <InputGroup>
                  <InputGroupAddon>₹</InputGroupAddon>
                  <InputGroupInput
                    {...aria}
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="No sump"
                    className="tabular-nums"
                    value={draft.sumpRate}
                    onChange={(event) => {
                      onChange({ ...draft, sumpRate: event.target.value });
                    }}
                  />
                  <InputGroupAddon align="end">/ Ha</InputGroupAddon>
                </InputGroup>
              )}
            </TextField>
          )}

          {system.supportsGroup ? (
            <TextField
              id="group-total-area"
              label="Group's total area"
              optional
              error={problems.group_total_area}
              description="Farmers sharing one water source: everyone's land, at least these crops'. Empty for one farmer."
              className="sm:col-span-2"
            >
              {(aria) => (
                <InputGroup className="sm:max-w-1/2">
                  <InputGroupInput
                    {...aria}
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="Quoting alone"
                    className="tabular-nums"
                    value={draft.groupTotalArea}
                    onChange={(event) => {
                      onChange({ ...draft, groupTotalArea: event.target.value });
                    }}
                  />
                  <InputGroupAddon align="end">Ha</InputGroupAddon>
                </InputGroup>
              )}
            </TextField>
          ) : null}

          {isSprinkler ? (
            <div className="flex flex-col gap-2 sm:col-span-2">
              <FieldLabel id="nozzle-label">Nozzle</FieldLabel>
              <RadioGroup<Nozzle>
                aria-labelledby="nozzle-label"
                aria-describedby={problems.nozzle === undefined ? undefined : "nozzle-error"}
                value={draft.nozzle}
                onValueChange={(nozzle) => {
                  onChange({ ...draft, nozzle });
                }}
                className="flex-row flex-wrap gap-5"
              >
                {NOZZLES.map((nozzle) => (
                  <label key={nozzle} className="flex items-center gap-2 text-sm text-foreground">
                    <RadioGroupItem value={nozzle} />
                    {NOZZLE_LABELS[nozzle]}
                  </label>
                ))}
              </RadioGroup>
              <p className="text-xs text-muted-foreground">
                The pipe size follows the area: the result names it.
              </p>
              {problems.nozzle === undefined ? null : (
                <p id="nozzle-error" className="text-xs text-danger">
                  {problems.nozzle}
                </p>
              )}
            </div>
          ) : null}
        </FieldGroup>
      </CardContent>
    </Card>
  );
}
