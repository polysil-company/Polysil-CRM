import type {
  CalculateRequest,
  Nozzle,
  SubsidyCropRequest,
  SubsidyLineRequest,
  SystemConfig,
  SystemType,
} from "@/features/subsidy/api/subsidy.schemas";
import { createRequestId } from "@/lib/api/request-id";

/**
 * SUBS-002 · What the designer has typed on one system's calculator, and how it becomes a
 * `POST /subsidy/calculate` request. Every value stays the string the designer typed, so a
 * decimal never passes through floating point on its way to the backend. Problems are keyed by
 * the backend's own field paths (`crops[0].area`), so a local check and a 422 land on the same
 * input.
 */

export interface DraftLine {
  readonly key: string;
  readonly description: string;
  readonly uom: string;
  readonly rate: string;
  readonly qty: string;
}

export interface DraftCrop {
  readonly key: string;
  readonly crop: string | null;
  readonly interCrop: string | null;
  readonly area: string;
  readonly cropSpacing: string;
  readonly lateralSpacing: string;
  readonly lines: readonly DraftLine[];
}

export interface CalculatorDraft {
  readonly systemType: SystemType;
  readonly crops: readonly DraftCrop[];
  readonly headLines: readonly DraftLine[];
  readonly sumpRate: string;
  /** Empty for a farmer quoting alone. */
  readonly groupTotalArea: string;
  readonly installationRate: string;
  readonly nozzle: Nozzle;
}

/** Field path → what is wrong, in words. */
export type DraftProblems = Readonly<Record<string, string>>;

export interface CalculationPlan {
  /** Null while something required is missing or wrong: nothing is sent. */
  readonly request: CalculateRequest | null;
  readonly problems: DraftProblems;
  /** Required inputs not given yet — not mistakes, so they are not shown as errors. */
  readonly missing: readonly string[];
}

const MAX_DECIMALS = { money: 2, area: 3, spacing: 2, qty: 3 } as const;

export function emptyLine(): DraftLine {
  return { key: createRequestId(), description: "", uom: "", rate: "", qty: "" };
}

export function emptyCrop(): DraftCrop {
  return {
    key: createRequestId(),
    crop: null,
    interCrop: null,
    area: "",
    cropSpacing: "",
    lateralSpacing: "",
    lines: [emptyLine()],
  };
}

export function emptyDraft(systemType: SystemType): CalculatorDraft {
  return {
    systemType,
    crops: [emptyCrop()],
    headLines: [emptyLine()],
    sumpRate: "",
    groupTotalArea: "",
    installationRate: "",
    nozzle: "plastic",
  };
}

/** "12.50" with at most `places` decimals, never negative; null when it isn't one. */
function decimalProblem(value: string, places: number, what: string): string | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return `Enter ${what} as a number, like 1.25.`;
  const decimals = trimmed.split(".")[1]?.length ?? 0;
  if (decimals > places) {
    return `Use at most ${String(places)} decimal${places === 1 ? "" : "s"}.`;
  }
  return null;
}

function positiveProblem(value: string, places: number, what: string): string | null {
  const problem = decimalProblem(value, places, what);
  if (problem !== null) return problem;
  return /[1-9]/.test(value) ? null : `${capitalise(what)} must be more than 0.`;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A row the designer hasn't started is left out rather than refused. */
export function isBlankLine(line: DraftLine): boolean {
  return (
    line.description.trim() === "" &&
    line.uom.trim() === "" &&
    line.rate.trim() === "" &&
    line.qty.trim() === ""
  );
}

function lineProblems(
  lines: readonly DraftLine[],
  path: string,
  problems: Record<string, string>,
): SubsidyLineRequest[] {
  const out: SubsidyLineRequest[] = [];
  lines
    .filter((line) => !isBlankLine(line))
    .forEach((line, index) => {
      const at = `${path}[${String(index)}]`;
      if (line.description.trim() === "") problems[`${at}.description`] = "Name the item.";
      if (line.uom.trim() === "") problems[`${at}.uom`] = "Give its unit, like Mtr. or No.";
      const rate = decimalProblem(line.rate, MAX_DECIMALS.money, "the rate");
      if (rate !== null) problems[`${at}.rate`] = rate;
      const qty = decimalProblem(line.qty, MAX_DECIMALS.qty, "the quantity");
      if (qty !== null) problems[`${at}.qty`] = qty;
      out.push({
        description: line.description.trim(),
        uom: line.uom.trim(),
        rate: line.rate.trim(),
        qty: line.qty.trim(),
      });
    });
  return out;
}

/**
 * The request for a draft, or why there isn't one yet. Keys a system doesn't take are left
 * out: Sprinkler sends no lines, no head unit and no group; the others send no nozzle.
 */
export function planCalculation(
  draft: CalculatorDraft,
  system: SystemConfig,
  /** The lead's scheme for an application; null leaves the backend's default (GGRC). */
  scheme: string | null = null,
): CalculationPlan {
  const problems: Record<string, string> = {};
  const missing: string[] = [];
  const isSprinkler = draft.systemType === "sprinkler";

  const crops: SubsidyCropRequest[] = draft.crops
    .slice(0, system.cropCountMax)
    .map((crop, index) => {
      const at = `crops[${String(index)}]`;
      if (crop.area.trim() === "") {
        missing.push(`${at}.area`);
      } else if (isSprinkler) {
        if (!(system.sprinklerAreas ?? []).includes(crop.area)) {
          problems[`${at}.area`] = "Choose one of the scheme's areas.";
        }
      } else {
        const problem = positiveProblem(crop.area, MAX_DECIMALS.area, "the area");
        if (problem !== null) problems[`${at}.area`] = problem;
      }
      if (crop.lateralSpacing.trim() === "") {
        missing.push(`${at}.lateral_spacing`);
      } else {
        const problem = positiveProblem(crop.lateralSpacing, MAX_DECIMALS.spacing, "the spacing");
        if (problem !== null) problems[`${at}.lateral_spacing`] = problem;
      }
      return {
        crop: crop.crop,
        inter_crop: crop.interCrop,
        area: crop.area.trim(),
        crop_spacing: crop.cropSpacing.trim(),
        lateral_spacing: crop.lateralSpacing.trim(),
        lines: isSprinkler ? [] : lineProblems(crop.lines, `${at}.lines`, problems),
      };
    });

  const headLines = system.hasHeadUnit ? lineProblems(draft.headLines, "head_lines", problems) : [];

  const optionalMoney = (value: string, field: string): string | undefined => {
    if (value.trim() === "") return undefined;
    const problem = decimalProblem(value, MAX_DECIMALS.money, "the rate");
    if (problem !== null) problems[field] = problem;
    return value.trim();
  };
  const installation = optionalMoney(draft.installationRate, "installation_rate_per_ha");
  const sump = isSprinkler ? undefined : optionalMoney(draft.sumpRate, "sump.rate_per_ha");

  let group: string | undefined;
  if (system.supportsGroup && draft.groupTotalArea.trim() !== "") {
    const problem = positiveProblem(draft.groupTotalArea, MAX_DECIMALS.area, "the group's area");
    if (problem === null) group = draft.groupTotalArea.trim();
    else problems.group_total_area = problem;
  }

  if (missing.length > 0 || Object.keys(problems).length > 0) {
    return { request: null, problems, missing };
  }

  const request: CalculateRequest = {
    ...(scheme === null ? {} : { scheme }),
    system_type: draft.systemType,
    crops,
    ...(system.hasHeadUnit ? { head_lines: headLines } : {}),
    ...(sump === undefined ? {} : { sump: { rate_per_ha: sump } }),
    ...(group === undefined ? {} : { group_total_area: group }),
    ...(installation === undefined ? {} : { installation_rate_per_ha: installation }),
    ...(isSprinkler ? { nozzle: draft.nozzle } : {}),
  };
  return { request, problems, missing };
}

/**
 * Each row's field path. A path counts only the rows that are sent, skipping blank ones, so
 * `crops[0].lines[1]` is the second filled row, wherever it sits on screen.
 */
export function linePaths(
  lines: readonly DraftLine[],
  base: string,
): Readonly<Record<string, string>> {
  const paths: Record<string, string> = {};
  let index = 0;
  for (const line of lines) {
    if (isBlankLine(line)) continue;
    paths[line.key] = `${base}[${String(index)}]`;
    index += 1;
  }
  return paths;
}

/** Splits `code: sentence` on the first colon. A warning without a code is all sentence. */
export function readWarning(warning: string): { code: string; sentence: string } {
  const at = warning.indexOf(":");
  if (at <= 0) return { code: "", sentence: warning.trim() };
  return { code: warning.slice(0, at).trim(), sentence: warning.slice(at + 1).trim() };
}
