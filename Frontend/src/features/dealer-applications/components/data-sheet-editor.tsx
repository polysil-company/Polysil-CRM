"use client";

import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  AREA_UNITS,
  DATA_SHEET_ROW_LIMITS,
  INSTALLATION_SCOPES,
  type AreaUnit,
  type InstallationScope,
} from "@/features/dealer-applications/api/data-sheet.schemas";
import {
  EMPTY_INSTALLATION,
  EMPTY_MANPOWER,
  EMPTY_WORKING_CAPITAL,
  type DataSheetDraft,
  type DataSheetProblems,
} from "@/features/dealer-applications/lib/data-sheet-draft";
import {
  AREA_UNIT_LABELS,
  INSTALLATION_SCOPE_LABELS,
} from "@/features/dealer-applications/lib/dealer-application-labels";

import { TextArea, TextField } from "./application-inputs";

/**
 * CHNL-007, CHNL-008 · The data sheet's parts of the application form (FS-071), shared by
 * staff's Edit details and the applicant's own page. Each part slots into the form's own
 * groups: the business facts, the bank's details, then the sheet's own sections.
 */
interface SheetProps {
  idPrefix: string;
  draft: DataSheetDraft;
  onChange: (next: DataSheetDraft) => void;
  problems: DataSheetProblems;
}

function setter(
  draft: DataSheetDraft,
  onChange: (next: DataSheetDraft) => void,
): <TKey extends keyof DataSheetDraft>(key: TKey, value: DataSheetDraft[TKey]) => void {
  return (key, value) => {
    onChange({ ...draft, [key]: value });
  };
}

/** Telephone, when the firm was set up, and where it is to be appointed. */
export function DataSheetBusinessFields({
  idPrefix,
  draft,
  onChange,
  problems,
  today,
}: SheetProps & { today: string }): React.JSX.Element {
  const set = setter(draft, onChange);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <TextField
        id={`${idPrefix}-telephone`}
        label="Telephone"
        optional
        inputMode="tel"
        maxLength={32}
        value={draft.telephone}
        error={problems.telephone}
        onChange={(value) => {
          set("telephone", value);
        }}
      />
      <TextField
        id={`${idPrefix}-established`}
        label="Established on"
        optional
        type="date"
        value={draft.establishedOn}
        error={problems.established_on}
        max={today}
        onChange={(value) => {
          set("establishedOn", value);
        }}
      />
      <TextField
        id={`${idPrefix}-appointment`}
        label="Place of appointment"
        optional
        maxLength={200}
        description="The town or area the firm is to serve."
        value={draft.appointmentPlace}
        error={problems.appointment_place}
        onChange={(value) => {
          set("appointmentPlace", value);
        }}
      />
    </div>
  );
}

/** The bank's name, branch and address, beside the account. */
export function DataSheetBankFields({
  idPrefix,
  draft,
  onChange,
  problems,
}: SheetProps): React.JSX.Element {
  const set = setter(draft, onChange);
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id={`${idPrefix}-bank`}
          label="Bank"
          optional
          maxLength={200}
          value={draft.bankName}
          error={problems.bank_name}
          onChange={(value) => {
            set("bankName", value);
          }}
        />
        <TextField
          id={`${idPrefix}-branch`}
          label="Branch"
          optional
          maxLength={200}
          value={draft.bankBranch}
          error={problems.bank_branch}
          onChange={(value) => {
            set("bankBranch", value);
          }}
        />
      </div>
      <TextArea
        id={`${idPrefix}-bank-address`}
        label="Branch address"
        optional
        value={draft.bankAddress}
        error={problems.bank_address}
        onChange={(value) => {
          set("bankAddress", value);
        }}
      />
    </>
  );
}

/** Working capital, premises and vehicles, people, and work done before. */
export function DataSheetSections({
  idPrefix,
  draft,
  onChange,
  problems,
  totalLakhs,
}: SheetProps & {
  /** The backend's total of the saved rows and other sources, when it has one. */
  totalLakhs: string | null;
}): React.JSX.Element {
  const set = setter(draft, onChange);
  return (
    <>
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">Working capital</legend>
        <RowsEditor
          label="Facility"
          rows={draft.workingCapital}
          limit={DATA_SHEET_ROW_LIMITS.workingCapital}
          empty={EMPTY_WORKING_CAPITAL}
          error={problems.working_capital}
          errorId={`${idPrefix}-capital-error`}
          addLabel="Add a facility"
          onChange={(rows) => {
            set("workingCapital", rows);
          }}
          render={(row, index, update) => (
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                id={`${idPrefix}-capital-${String(index)}-facility`}
                label={`Facility ${String(index + 1)}`}
                maxLength={100}
                description={index === 0 ? "Own funds, a cash credit, a term loan…" : undefined}
                value={row.facility}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, facility: value });
                }}
              />
              <TextField
                id={`${idPrefix}-capital-${String(index)}-amount`}
                label="Amount, in lakhs"
                inputMode="decimal"
                value={row.amountLakhs}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, amountLakhs: value });
                }}
              />
            </div>
          )}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={`${idPrefix}-other-sources`}
            label="Other sources, in lakhs"
            optional
            inputMode="decimal"
            value={draft.otherSourcesLakhs}
            error={problems.other_sources_lakhs}
            onChange={(value) => {
              set("otherSourcesLakhs", value);
            }}
          />
          {totalLakhs === null ? null : (
            <div className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-foreground">Total, as saved</span>
              <span className="text-foreground tabular-nums">{totalLakhs} lakhs</span>
            </div>
          )}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">
          Premises and vehicles
        </legend>
        <Field>
          <FieldLabel id={`${idPrefix}-unit-label`}>Areas in</FieldLabel>
          <RadioGroup<AreaUnit>
            aria-labelledby={`${idPrefix}-unit-label`}
            value={draft.areaUnit}
            onValueChange={(value) => {
              set("areaUnit", value);
            }}
            className="flex-row flex-wrap gap-5"
          >
            {AREA_UNITS.map((unit) => (
              <label key={unit} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={unit} />
                {AREA_UNIT_LABELS[unit]}
              </label>
            ))}
          </RadioGroup>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={`${idPrefix}-office-area`}
            label="Office area"
            optional
            inputMode="decimal"
            value={draft.officeArea}
            error={problems.office_area}
            onChange={(value) => {
              set("officeArea", value);
            }}
          />
          <TextField
            id={`${idPrefix}-godown-area`}
            label="Godown area"
            optional
            inputMode="decimal"
            value={draft.godownArea}
            error={problems.godown_area}
            onChange={(value) => {
              set("godownArea", value);
            }}
          />
          <TextField
            id={`${idPrefix}-two-wheelers`}
            label="Two-wheelers"
            optional
            inputMode="numeric"
            value={draft.twoWheelers}
            error={problems.two_wheelers}
            onChange={(value) => {
              set("twoWheelers", value);
            }}
          />
          <TextField
            id={`${idPrefix}-cars`}
            label="Cars"
            optional
            inputMode="numeric"
            value={draft.cars}
            error={problems.cars}
            onChange={(value) => {
              set("cars", value);
            }}
          />
        </div>
        <TextField
          id={`${idPrefix}-other-vehicles`}
          label="Other vehicles"
          optional
          maxLength={200}
          description="A tempo, a tractor… with how many."
          value={draft.otherVehicles}
          error={problems.other_vehicles}
          onChange={(value) => {
            set("otherVehicles", value);
          }}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">People</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={`${idPrefix}-sales-executives`}
            label="Sales executives"
            optional
            inputMode="numeric"
            value={draft.salesExecutives}
            error={problems.sales_executives}
            onChange={(value) => {
              set("salesExecutives", value);
            }}
          />
          <TextField
            id={`${idPrefix}-technicians`}
            label="Technicians"
            optional
            inputMode="numeric"
            value={draft.technicians}
            error={problems.technicians}
            onChange={(value) => {
              set("technicians", value);
            }}
          />
        </div>
        <RowsEditor
          label="Group"
          rows={draft.manpower}
          limit={DATA_SHEET_ROW_LIMITS.manpower}
          empty={EMPTY_MANPOWER}
          error={problems.manpower}
          errorId={`${idPrefix}-manpower-error`}
          addLabel="Add a group of people"
          onChange={(rows) => {
            set("manpower", rows);
          }}
          render={(row, index, update) => (
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                id={`${idPrefix}-manpower-${String(index)}-category`}
                label={`Group ${String(index + 1)}`}
                maxLength={100}
                description={index === 0 ? "Plumbers, fitters, accounts…" : undefined}
                value={row.category}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, category: value });
                }}
              />
              <TextField
                id={`${idPrefix}-manpower-${String(index)}-people`}
                label="How many"
                inputMode="numeric"
                value={row.people}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, people: value });
                }}
              />
              <TextField
                id={`${idPrefix}-manpower-${String(index)}-qualification`}
                label="Qualification"
                optional
                maxLength={100}
                value={row.qualification}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, qualification: value });
                }}
              />
              <TextField
                id={`${idPrefix}-manpower-${String(index)}-work`}
                label="Type of work"
                optional
                maxLength={100}
                value={row.workType}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, workType: value });
                }}
              />
              <TextField
                id={`${idPrefix}-manpower-${String(index)}-experience`}
                label="Experience, in years"
                optional
                inputMode="numeric"
                value={row.experienceYears}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, experienceYears: value });
                }}
              />
            </div>
          )}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">
          Installations done before
        </legend>
        <RowsEditor
          label="Installation"
          rows={draft.installations}
          limit={DATA_SHEET_ROW_LIMITS.installations}
          empty={EMPTY_INSTALLATION}
          error={problems.previous_installations}
          errorId={`${idPrefix}-installations-error`}
          addLabel="Add an installation"
          onChange={(rows) => {
            set("installations", rows);
          }}
          render={(row, index, update) => (
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                id={`${idPrefix}-installation-${String(index)}-year`}
                label={`Year, installation ${String(index + 1)}`}
                inputMode="numeric"
                maxLength={4}
                value={row.year}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, year: value });
                }}
              />
              <TextField
                id={`${idPrefix}-installation-${String(index)}-customers`}
                label="Customers"
                inputMode="numeric"
                value={row.customers}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, customers: value });
                }}
              />
              <div className="sm:col-span-2">
                <TextField
                  id={`${idPrefix}-installation-${String(index)}-description`}
                  label="What was done"
                  maxLength={300}
                  value={row.description}
                  error={undefined}
                  onChange={(value) => {
                    update({ ...row, description: value });
                  }}
                />
              </div>
              <Field>
                <FieldLabel id={`${idPrefix}-installation-${String(index)}-scope`}>
                  Scope
                </FieldLabel>
                <RadioGroup<InstallationScope>
                  aria-labelledby={`${idPrefix}-installation-${String(index)}-scope`}
                  value={row.scope}
                  onValueChange={(value) => {
                    update({ ...row, scope: value });
                  }}
                  className="flex-row flex-wrap gap-4"
                >
                  {INSTALLATION_SCOPES.map((scope) => (
                    <label key={scope} className="flex items-center gap-2 text-sm text-foreground">
                      <RadioGroupItem value={scope} />
                      {INSTALLATION_SCOPE_LABELS[scope]}
                    </label>
                  ))}
                </RadioGroup>
              </Field>
              <TextField
                id={`${idPrefix}-installation-${String(index)}-cost`}
                label="Cost, in lakhs"
                inputMode="decimal"
                value={row.costLakhs}
                error={undefined}
                onChange={(value) => {
                  update({ ...row, costLakhs: value });
                }}
              />
            </div>
          )}
        />
      </fieldset>
    </>
  );
}

/**
 * A table typed in as rows, each in its own box (they're too wide for one line on a phone),
 * with a remove button per row and an add button up to the backend's limit. The table's
 * problem names its row.
 */
function RowsEditor<TRow>({
  label,
  rows,
  limit,
  empty,
  error,
  errorId,
  addLabel,
  onChange,
  render,
}: {
  label: string;
  rows: readonly TRow[];
  limit: number;
  empty: TRow;
  error: string | undefined;
  errorId: string;
  addLabel: string;
  onChange: (rows: readonly TRow[]) => void;
  render: (row: TRow, index: number, update: (next: TRow) => void) => React.ReactNode;
}): React.JSX.Element {
  return (
    <Field data-invalid={error === undefined ? undefined : true} className="gap-3">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">None added.</p>
      ) : (
        <ol
          className="flex flex-col gap-3"
          aria-describedby={error === undefined ? undefined : errorId}
        >
          {rows.map((row, index) => (
            <li
              // Rows have no id of their own; their place is their identity while typing.
              key={index}
              className="flex items-start gap-2 rounded-lg border border-border p-3"
            >
              <div className="min-w-0 flex-1">
                {render(row, index, (next) => {
                  onChange(rows.map((item, at) => (at === index ? next : item)));
                })}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${label.toLowerCase()} ${String(index + 1)}`}
                onClick={() => {
                  onChange(rows.filter((_, at) => at !== index));
                }}
              >
                <Icon icon={Delete02Icon} />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <FieldError id={errorId}>{error}</FieldError>
      {rows.length >= limit ? (
        <p className="text-xs text-muted-foreground">
          At most {String(limit)}. Remove one to add another.
        </p>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() => {
            onChange([...rows, empty]);
          }}
        >
          <Icon icon={Add01Icon} />
          {addLabel}
        </Button>
      )}
    </Field>
  );
}
