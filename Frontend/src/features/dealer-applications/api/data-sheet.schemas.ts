import { z } from "zod";

/**
 * CHNL-007, CHNL-008 · The application's data sheet (FS-071): what Polysil's printed dealer and
 * distributor form asks beyond the firm, tax and bank details. The same fields on staff's view
 * and the applicant's own page. Contract: `backend/docs/api/dealer-applications.md`
 * (`DealerApplicationFields`, `WorkingCapitalRow`, `ManpowerRow`, `InstallationRow`).
 *
 * Every field is read leniently (missing is "not filled"): a backend before migration 078 sends
 * none of them, and the screens must still work there.
 */

export const PARTNER_TYPES = ["dealer", "distributor"] as const;
export type PartnerType = (typeof PARTNER_TYPES)[number];

export const AREA_UNITS = ["sq_ft", "sq_m"] as const;
export type AreaUnit = (typeof AREA_UNITS)[number];

export const INSTALLATION_SCOPES = ["supply", "installation", "both"] as const;
export type InstallationScope = (typeof INSTALLATION_SCOPES)[number];

/** The backend's limits on each table (FS-071). */
export const DATA_SHEET_ROW_LIMITS = {
  workingCapital: 10,
  manpower: 20,
  installations: 50,
} as const;

/** A decimal string as the backend sends it; a number is read as one too. */
const decimal = z.union([z.string(), z.number()]).transform(String);

const workingCapitalRowSchema = z.object({ facility: z.string(), amount_lakhs: decimal });

const manpowerRowSchema = z.object({
  category: z.string(),
  qualification: z.string().nullish(),
  work_type: z.string().nullish(),
  experience_years: z.number().int().nullish(),
  people: z.number().int(),
});

const installationRowSchema = z.object({
  year: z.number().int(),
  customers: z.number().int(),
  description: z.string(),
  scope: z.enum(INSTALLATION_SCOPES),
  cost_lakhs: decimal,
});

/** The data sheet's wire fields, spread into the staff and the applicant views. */
export const dataSheetWireShape = {
  telephone: z.string().nullish(),
  established_on: z.string().nullish(),
  bank_name: z.string().nullish(),
  bank_branch: z.string().nullish(),
  bank_address: z.string().nullish(),
  working_capital: z.array(workingCapitalRowSchema).nullish(),
  other_sources_lakhs: decimal.nullish(),
  /** The rows plus other sources; null when neither is filled. */
  working_capital_total_lakhs: decimal.nullish(),
  two_wheelers: z.number().int().nullish(),
  cars: z.number().int().nullish(),
  other_vehicles: z.string().nullish(),
  office_area: decimal.nullish(),
  godown_area: decimal.nullish(),
  area_unit: z.enum(AREA_UNITS).nullish(),
  manpower: z.array(manpowerRowSchema).nullish(),
  previous_installations: z.array(installationRowSchema).nullish(),
  sales_executives: z.number().int().nullish(),
  technicians: z.number().int().nullish(),
  appointment_place: z.string().nullish(),
};

type DataSheetWire = z.output<z.ZodObject<typeof dataSheetWireShape>>;

export interface WorkingCapitalRow {
  readonly facility: string;
  readonly amountLakhs: string;
}

export interface ManpowerRow {
  readonly category: string;
  readonly qualification: string | null;
  readonly workType: string | null;
  readonly experienceYears: number | null;
  readonly people: number;
}

export interface InstallationRow {
  readonly year: number;
  readonly customers: number;
  readonly description: string;
  readonly scope: InstallationScope;
  readonly costLakhs: string;
}

export interface DataSheet {
  readonly telephone: string | null;
  /** `YYYY-MM-DD`. */
  readonly establishedOn: string | null;
  readonly bankName: string | null;
  readonly bankBranch: string | null;
  readonly bankAddress: string | null;
  readonly workingCapital: readonly WorkingCapitalRow[];
  readonly otherSourcesLakhs: string | null;
  readonly workingCapitalTotalLakhs: string | null;
  readonly twoWheelers: number | null;
  readonly cars: number | null;
  readonly otherVehicles: string | null;
  readonly officeArea: string | null;
  readonly godownArea: string | null;
  /** Square feet unless the backend says otherwise. */
  readonly areaUnit: AreaUnit;
  readonly manpower: readonly ManpowerRow[];
  readonly previousInstallations: readonly InstallationRow[];
  readonly salesExecutives: number | null;
  readonly technicians: number | null;
  readonly appointmentPlace: string | null;
}

export function toDataSheet(wire: Partial<DataSheetWire>): DataSheet {
  return {
    telephone: wire.telephone ?? null,
    establishedOn: wire.established_on?.slice(0, 10) ?? null,
    bankName: wire.bank_name ?? null,
    bankBranch: wire.bank_branch ?? null,
    bankAddress: wire.bank_address ?? null,
    workingCapital: (wire.working_capital ?? []).map((row) => ({
      facility: row.facility,
      amountLakhs: row.amount_lakhs,
    })),
    otherSourcesLakhs: wire.other_sources_lakhs ?? null,
    workingCapitalTotalLakhs: wire.working_capital_total_lakhs ?? null,
    twoWheelers: wire.two_wheelers ?? null,
    cars: wire.cars ?? null,
    otherVehicles: wire.other_vehicles ?? null,
    officeArea: wire.office_area ?? null,
    godownArea: wire.godown_area ?? null,
    areaUnit: wire.area_unit ?? "sq_ft",
    manpower: (wire.manpower ?? []).map((row) => ({
      category: row.category,
      qualification: row.qualification ?? null,
      workType: row.work_type ?? null,
      experienceYears: row.experience_years ?? null,
      people: row.people,
    })),
    previousInstallations: (wire.previous_installations ?? []).map((row) => ({
      year: row.year,
      customers: row.customers,
      description: row.description,
      scope: row.scope,
      costLakhs: row.cost_lakhs,
    })),
    salesExecutives: wire.sales_executives ?? null,
    technicians: wire.technicians ?? null,
    appointmentPlace: wire.appointment_place ?? null,
  };
}

/** PATCH: the data sheet's fields, only what changes; null clears. */
export interface DataSheetRequest {
  readonly telephone?: string | null;
  readonly established_on?: string | null;
  readonly bank_name?: string | null;
  readonly bank_branch?: string | null;
  readonly bank_address?: string | null;
  readonly working_capital?: readonly { facility: string; amount_lakhs: string }[] | null;
  readonly other_sources_lakhs?: string | null;
  readonly two_wheelers?: number | null;
  readonly cars?: number | null;
  readonly other_vehicles?: string | null;
  readonly office_area?: string | null;
  readonly godown_area?: string | null;
  readonly area_unit?: AreaUnit | null;
  readonly manpower?:
    | readonly {
        category: string;
        qualification: string | null;
        work_type: string | null;
        experience_years: number | null;
        people: number;
      }[]
    | null;
  readonly previous_installations?:
    | readonly {
        year: number;
        customers: number;
        description: string;
        scope: InstallationScope;
        cost_lakhs: string;
      }[]
    | null;
  readonly sales_executives?: number | null;
  readonly technicians?: number | null;
  readonly appointment_place?: string | null;
}
