import type {
  AreaUnit,
  DataSheet,
  DataSheetRequest,
  InstallationScope,
} from "@/features/dealer-applications/api/data-sheet.schemas";

/**
 * CHNL-007, CHNL-008 · The data sheet as a form holds it: text as typed, rows as lists. The
 * checks are the backend's own (`api/schemas/dealer_applications.py`), so a refusal is rare;
 * the backend checks again.
 */

export interface WorkingCapitalDraft {
  readonly facility: string;
  readonly amountLakhs: string;
}

export interface ManpowerDraft {
  readonly category: string;
  readonly qualification: string;
  readonly workType: string;
  readonly experienceYears: string;
  readonly people: string;
}

export interface InstallationDraft {
  readonly year: string;
  readonly customers: string;
  readonly description: string;
  readonly scope: InstallationScope;
  readonly costLakhs: string;
}

export interface DataSheetDraft {
  readonly telephone: string;
  readonly establishedOn: string;
  readonly appointmentPlace: string;
  readonly bankName: string;
  readonly bankBranch: string;
  readonly bankAddress: string;
  readonly workingCapital: readonly WorkingCapitalDraft[];
  readonly otherSourcesLakhs: string;
  readonly officeArea: string;
  readonly godownArea: string;
  readonly areaUnit: AreaUnit;
  readonly twoWheelers: string;
  readonly cars: string;
  readonly otherVehicles: string;
  readonly salesExecutives: string;
  readonly technicians: string;
  readonly manpower: readonly ManpowerDraft[];
  readonly installations: readonly InstallationDraft[];
}

/** Where a problem shows: a field, or a whole table (the row is named in the message). */
export type DataSheetProblemKey =
  | "telephone"
  | "established_on"
  | "appointment_place"
  | "bank_name"
  | "bank_branch"
  | "bank_address"
  | "working_capital"
  | "other_sources_lakhs"
  | "office_area"
  | "godown_area"
  | "two_wheelers"
  | "cars"
  | "other_vehicles"
  | "sales_executives"
  | "technicians"
  | "manpower"
  | "previous_installations";

export type DataSheetProblems = Partial<Record<DataSheetProblemKey, string>>;

const LAKHS = /^\d{1,5}(\.\d{1,2})?$/;
const AREA = /^\d{1,7}(\.\d{1,2})?$/;
const LAKHS_HINT = "Lakhs, like 12.5 (at most two decimals).";

function text(value: number | null): string {
  return value === null ? "" : String(value);
}

export const EMPTY_WORKING_CAPITAL: WorkingCapitalDraft = { facility: "", amountLakhs: "" };
export const EMPTY_MANPOWER: ManpowerDraft = {
  category: "",
  qualification: "",
  workType: "",
  experienceYears: "",
  people: "",
};
export const EMPTY_INSTALLATION: InstallationDraft = {
  year: "",
  customers: "",
  description: "",
  scope: "both",
  costLakhs: "",
};

export function dataSheetDraftOf(sheet: DataSheet): DataSheetDraft {
  return {
    telephone: sheet.telephone ?? "",
    establishedOn: sheet.establishedOn ?? "",
    appointmentPlace: sheet.appointmentPlace ?? "",
    bankName: sheet.bankName ?? "",
    bankBranch: sheet.bankBranch ?? "",
    bankAddress: sheet.bankAddress ?? "",
    workingCapital: sheet.workingCapital.map((row) => ({ ...row })),
    otherSourcesLakhs: sheet.otherSourcesLakhs ?? "",
    officeArea: sheet.officeArea ?? "",
    godownArea: sheet.godownArea ?? "",
    areaUnit: sheet.areaUnit,
    twoWheelers: text(sheet.twoWheelers),
    cars: text(sheet.cars),
    otherVehicles: sheet.otherVehicles ?? "",
    salesExecutives: text(sheet.salesExecutives),
    technicians: text(sheet.technicians),
    manpower: sheet.manpower.map((row) => ({
      category: row.category,
      qualification: row.qualification ?? "",
      workType: row.workType ?? "",
      experienceYears: text(row.experienceYears),
      people: String(row.people),
    })),
    installations: sheet.previousInstallations.map((row) => ({
      year: String(row.year),
      customers: String(row.customers),
      description: row.description,
      scope: row.scope,
      costLakhs: row.costLakhs,
    })),
  };
}

function wholeNumber(value: string, max: number): boolean {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) && Number(trimmed) <= max;
}

/** A row nobody typed in: left out when saving, rather than refused. */
function isBlank(row: object): boolean {
  return Object.entries(row).every(
    ([key, value]) => key === "scope" || (typeof value === "string" && value.trim() === ""),
  );
}

function rowProblem(index: number, problem: string | null): string | null {
  return problem === null ? null : `Row ${String(index + 1)}: ${problem}`;
}

function firstProblem<TRow extends object>(
  rows: readonly TRow[],
  check: (row: TRow) => string | null,
): string | null {
  for (const [index, row] of rows.entries()) {
    if (isBlank(row)) continue;
    const problem = rowProblem(index, check(row));
    if (problem !== null) return problem;
  }
  return null;
}

/** What reads wrong before the backend sees it; `today` is `YYYY-MM-DD` in IST. */
export function dataSheetProblems(draft: DataSheetDraft, today: string): DataSheetProblems {
  const problems: DataSheetProblems = {};
  const optionalWhole = (key: DataSheetProblemKey, value: string, max: number): void => {
    if (value.trim() !== "" && !wholeNumber(value, max)) {
      problems[key] = `A whole number, up to ${String(max)}.`;
    }
  };
  const established = draft.establishedOn.trim();
  if (established !== "" && (established < "1900-01-01" || established > today)) {
    problems.established_on = "From 1900, and not after today.";
  }
  if (draft.otherSourcesLakhs.trim() !== "" && !LAKHS.test(draft.otherSourcesLakhs.trim())) {
    problems.other_sources_lakhs = LAKHS_HINT;
  }
  for (const [key, value] of [
    ["office_area", draft.officeArea],
    ["godown_area", draft.godownArea],
  ] as const) {
    if (value.trim() !== "" && !AREA.test(value.trim())) {
      problems[key] = "An area, like 1200 (at most two decimals).";
    }
  }
  optionalWhole("two_wheelers", draft.twoWheelers, 999);
  optionalWhole("cars", draft.cars, 999);
  optionalWhole("sales_executives", draft.salesExecutives, 9999);
  optionalWhole("technicians", draft.technicians, 9999);

  const capital = firstProblem(draft.workingCapital, (row) => {
    if (row.facility.trim() === "") return "name the facility.";
    if (!LAKHS.test(row.amountLakhs.trim())) return `the amount in ${LAKHS_HINT.toLowerCase()}`;
    return null;
  });
  if (capital !== null) problems.working_capital = capital;

  const people = firstProblem(draft.manpower, (row) => {
    if (row.category.trim() === "") return "name the category, like Plumber.";
    if (row.experienceYears.trim() !== "" && !wholeNumber(row.experienceYears, 80)) {
      return "experience in whole years, up to 80.";
    }
    if (!wholeNumber(row.people, 9999) || Number(row.people.trim()) < 1) {
      return "how many people, at least 1.";
    }
    return null;
  });
  if (people !== null) problems.manpower = people;

  const thisYear = Number(today.slice(0, 4));
  const installations = firstProblem(draft.installations, (row) => {
    const year = Number(row.year.trim());
    if (!/^\d{4}$/.test(row.year.trim()) || year < 1950 || year > thisYear) {
      return `the year, from 1950 to ${String(thisYear)}.`;
    }
    if (!wholeNumber(row.customers, 999999)) return "how many customers, a whole number.";
    if (row.description.trim() === "") return "describe the work.";
    if (!LAKHS.test(row.costLakhs.trim())) return `the cost in ${LAKHS_HINT.toLowerCase()}`;
    return null;
  });
  if (installations !== null) problems.previous_installations = installations;
  return problems;
}

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : Number(trimmed);
}

function workingCapitalBody(
  rows: readonly WorkingCapitalDraft[],
): DataSheetRequest["working_capital"] {
  const kept = rows.filter((row) => !isBlank(row));
  return kept.length === 0
    ? null
    : kept.map((row) => ({ facility: row.facility.trim(), amount_lakhs: row.amountLakhs.trim() }));
}

function manpowerBody(rows: readonly ManpowerDraft[]): DataSheetRequest["manpower"] {
  const kept = rows.filter((row) => !isBlank(row));
  return kept.length === 0
    ? null
    : kept.map((row) => ({
        category: row.category.trim(),
        qualification: textOrNull(row.qualification),
        work_type: textOrNull(row.workType),
        experience_years: numberOrNull(row.experienceYears),
        people: Number(row.people.trim()),
      }));
}

function installationsBody(
  rows: readonly InstallationDraft[],
): DataSheetRequest["previous_installations"] {
  const kept = rows.filter((row) => !isBlank(row));
  return kept.length === 0
    ? null
    : kept.map((row) => ({
        year: Number(row.year.trim()),
        customers: Number(row.customers.trim()),
        description: row.description.trim(),
        scope: row.scope,
        cost_lakhs: row.costLakhs.trim(),
      }));
}

/** The PATCH body's data-sheet part: only what changed; an emptied field or table clears it. */
export function changedDataSheet(draft: DataSheetDraft, initial: DataSheetDraft): DataSheetRequest {
  const body: Record<string, unknown> = {};
  const textField = (key: string, now: string, before: string): void => {
    if (now.trim() !== before.trim()) body[key] = textOrNull(now);
  };
  const numberField = (key: string, now: string, before: string): void => {
    if (now.trim() !== before.trim()) body[key] = numberOrNull(now);
  };
  textField("telephone", draft.telephone, initial.telephone);
  textField("established_on", draft.establishedOn, initial.establishedOn);
  textField("appointment_place", draft.appointmentPlace, initial.appointmentPlace);
  textField("bank_name", draft.bankName, initial.bankName);
  textField("bank_branch", draft.bankBranch, initial.bankBranch);
  textField("bank_address", draft.bankAddress, initial.bankAddress);
  textField("other_sources_lakhs", draft.otherSourcesLakhs, initial.otherSourcesLakhs);
  textField("office_area", draft.officeArea, initial.officeArea);
  textField("godown_area", draft.godownArea, initial.godownArea);
  if (draft.areaUnit !== initial.areaUnit) body.area_unit = draft.areaUnit;
  numberField("two_wheelers", draft.twoWheelers, initial.twoWheelers);
  numberField("cars", draft.cars, initial.cars);
  textField("other_vehicles", draft.otherVehicles, initial.otherVehicles);
  numberField("sales_executives", draft.salesExecutives, initial.salesExecutives);
  numberField("technicians", draft.technicians, initial.technicians);
  const same = (left: unknown, right: unknown): boolean =>
    JSON.stringify(left) === JSON.stringify(right);
  const capital = workingCapitalBody(draft.workingCapital);
  if (!same(capital, workingCapitalBody(initial.workingCapital))) body.working_capital = capital;
  const people = manpowerBody(draft.manpower);
  if (!same(people, manpowerBody(initial.manpower))) body.manpower = people;
  const installations = installationsBody(draft.installations);
  if (!same(installations, installationsBody(initial.installations))) {
    body.previous_installations = installations;
  }
  const result: DataSheetRequest = body;
  return result;
}
