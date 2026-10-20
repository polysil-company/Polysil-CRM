"use client";

import type * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  FIRM_TYPES,
  type DealerApplication,
  type DealerApplicationFieldsRequest,
  type FirmType,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import { FIRM_TYPE_LABELS } from "@/features/dealer-applications/lib/dealer-application-labels";

/**
 * CHNL-007 · The application's fields as a form keeps them: text for each, as typed. Shared by
 * staff's Edit details and the applicant's own page.
 */
export interface DealerFieldsDraft {
  readonly firmName: string;
  readonly contactName: string;
  readonly firmType: FirmType | null;
  readonly gstRegistered: boolean;
  readonly gstin: string;
  readonly pan: string;
  readonly address: string;
  readonly pincode: string;
  readonly email: string;
  readonly godownAddress: string;
  readonly yearsInBusiness: string;
  readonly currentBrands: string;
  readonly notes: string;
  readonly bankAccountName: string;
  /** Empty when the stored number is masked: typing one replaces it. */
  readonly bankAccountNo: string;
  readonly bankIfsc: string;
}

export type DealerField = keyof DealerApplicationFieldsRequest;
export type DealerFieldProblems = Partial<Record<DealerField, string>>;

export const GSTIN_PATTERN = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_PATTERN = /^[A-Z]{5}\d{4}[A-Z]$/;
const IFSC_PATTERN = /^[A-Z]{4}0[A-Z0-9]{6}$/;

/** A masked account number ("XXXX7890") isn't the number: the form starts empty instead. */
export function isMaskedAccount(value: string | null): boolean {
  return value !== null && /\D/.test(value);
}

export function draftOf(
  application: Pick<
    DealerApplication,
    | "firmName"
    | "contactName"
    | "firmType"
    | "gstRegistered"
    | "gstin"
    | "pan"
    | "address"
    | "pincode"
    | "email"
    | "godownAddress"
    | "yearsInBusiness"
    | "currentBrands"
    | "notes"
    | "bankAccountName"
    | "bankAccountNo"
    | "bankIfsc"
  >,
): DealerFieldsDraft {
  return {
    firmName: application.firmName,
    contactName: application.contactName,
    firmType: application.firmType,
    gstRegistered: application.gstRegistered,
    gstin: application.gstin ?? "",
    pan: application.pan ?? "",
    address: application.address ?? "",
    pincode: application.pincode ?? "",
    email: application.email ?? "",
    godownAddress: application.godownAddress ?? "",
    yearsInBusiness:
      application.yearsInBusiness === null ? "" : String(application.yearsInBusiness),
    currentBrands: application.currentBrands ?? "",
    notes: application.notes ?? "",
    bankAccountName: application.bankAccountName ?? "",
    bankAccountNo: isMaskedAccount(application.bankAccountNo)
      ? ""
      : (application.bankAccountNo ?? ""),
    bankIfsc: application.bankIfsc ?? "",
  };
}

/** What a field reads as, before the backend sees it; the backend checks again. */
export function fieldProblems(draft: DealerFieldsDraft): DealerFieldProblems {
  const problems: DealerFieldProblems = {};
  const gstin = draft.gstin.trim().toUpperCase();
  const pan = draft.pan.trim().toUpperCase();
  if (draft.firmName.trim() === "") problems.firm_name = "Enter the firm's name.";
  if (draft.contactName.trim() === "") problems.contact_name = "Enter whom to ask for.";
  if (draft.gstRegistered && gstin !== "" && !GSTIN_PATTERN.test(gstin)) {
    problems.gstin = "A GSTIN is 15 characters, like 24ABCDE1234F1Z5.";
  }
  if (pan !== "" && !PAN_PATTERN.test(pan))
    problems.pan = "A PAN is 10 characters, like ABCDE1234F.";
  if (
    !problems.gstin &&
    !problems.pan &&
    gstin !== "" &&
    pan !== "" &&
    gstin.slice(2, 12) !== pan
  ) {
    problems.pan = "Not the PAN inside the GSTIN.";
  }
  if (draft.pincode.trim() !== "" && !/^\d{6}$/.test(draft.pincode.trim())) {
    problems.pincode = "Six digits.";
  }
  if (draft.email.trim() !== "" && !/^\S+@\S+\.\S+$/.test(draft.email.trim())) {
    problems.email = "Enter an email address, like name@example.com.";
  }
  if (draft.yearsInBusiness.trim() !== "" && !/^\d{1,3}$/.test(draft.yearsInBusiness.trim())) {
    problems.years_in_business = "Whole years, like 5.";
  }
  if (draft.bankAccountNo.trim() !== "" && !/^\d{9,18}$/.test(draft.bankAccountNo.trim())) {
    problems.bank_account_no = "9 to 18 digits.";
  }
  const ifsc = draft.bankIfsc.trim().toUpperCase();
  if (ifsc !== "" && !IFSC_PATTERN.test(ifsc))
    problems.bank_ifsc = "An IFSC is 11 characters, like SBIN0001234.";
  return problems;
}

function textOrNull(value: string, upper = false): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return upper ? trimmed.toUpperCase() : trimmed;
}

/** The PATCH body: only what changed from `initial`; an emptied field clears it (null). */
export function changedFields(
  draft: DealerFieldsDraft,
  initial: DealerFieldsDraft,
): DealerApplicationFieldsRequest {
  const body: Record<string, unknown> = {};
  const text = (key: DealerField, now: string, before: string, upper = false): void => {
    if (now.trim() !== before.trim()) body[key] = textOrNull(now, upper);
  };
  if (draft.firmName.trim() !== initial.firmName.trim()) body.firm_name = draft.firmName.trim();
  if (draft.contactName.trim() !== initial.contactName.trim()) {
    body.contact_name = draft.contactName.trim();
  }
  if (draft.firmType !== initial.firmType) body.firm_type = draft.firmType;
  if (draft.gstRegistered !== initial.gstRegistered) body.gst_registered = draft.gstRegistered;
  text("gstin", draft.gstRegistered ? draft.gstin : "", initial.gstin, true);
  text("pan", draft.pan, initial.pan, true);
  text("address", draft.address, initial.address);
  text("pincode", draft.pincode, initial.pincode);
  text("email", draft.email, initial.email);
  text("godown_address", draft.godownAddress, initial.godownAddress);
  if (draft.yearsInBusiness.trim() !== initial.yearsInBusiness.trim()) {
    body.years_in_business =
      draft.yearsInBusiness.trim() === "" ? null : Number(draft.yearsInBusiness.trim());
  }
  text("current_brands", draft.currentBrands, initial.currentBrands);
  text("notes", draft.notes, initial.notes);
  text("bank_account_name", draft.bankAccountName, initial.bankAccountName);
  // a masked number starts empty: leaving it empty keeps the stored one
  if (draft.bankAccountNo.trim() !== "" && draft.bankAccountNo.trim() !== initial.bankAccountNo) {
    body.bank_account_no = draft.bankAccountNo.trim();
  }
  text("bank_ifsc", draft.bankIfsc, initial.bankIfsc, true);
  const result: DealerApplicationFieldsRequest = body;
  return result;
}

/**
 * The fields, in three groups: the firm and its tax numbers, the address, and the bank.
 * `gstinCheck` renders under a well-formed GSTIN (staff: the GST record; the applicant: its own
 * check).
 */
export function DealerFieldsEditor({
  idPrefix,
  draft,
  onDraftChange,
  problems,
  gstinCheck,
  maskedAccount = null,
}: {
  idPrefix: string;
  draft: DealerFieldsDraft;
  onDraftChange: (next: DealerFieldsDraft) => void;
  problems: DealerFieldProblems;
  gstinCheck?: (gstin: string) => React.ReactNode;
  /** The stored account number, masked, when the reader can't see it. */
  maskedAccount?: string | null;
}): React.JSX.Element {
  const set = <TKey extends keyof DealerFieldsDraft>(
    key: TKey,
    value: DealerFieldsDraft[TKey],
  ): void => {
    onDraftChange({ ...draft, [key]: value });
  };
  const gstin = draft.gstin.trim().toUpperCase();
  const id = (name: string): string => `${idPrefix}-${name}`;

  return (
    <div className="flex flex-col gap-6">
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">Firm and tax</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={id("firm")}
            label="Firm"
            value={draft.firmName}
            error={problems.firm_name}
            onChange={(value) => {
              set("firmName", value);
            }}
          />
          <TextField
            id={id("contact")}
            label="Contact person"
            value={draft.contactName}
            error={problems.contact_name}
            onChange={(value) => {
              set("contactName", value);
            }}
          />
        </div>
        <Field>
          <FieldLabel id={id("firm-type-label")}>Firm type</FieldLabel>
          <RadioGroup<FirmType | null>
            aria-labelledby={id("firm-type-label")}
            value={draft.firmType}
            onValueChange={(value) => {
              set("firmType", value);
            }}
            className="flex-row flex-wrap gap-5"
          >
            {FIRM_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={type} />
                {FIRM_TYPE_LABELS[type]}
              </label>
            ))}
          </RadioGroup>
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground">
          <Checkbox
            checked={draft.gstRegistered}
            onCheckedChange={(checked) => {
              set("gstRegistered", checked);
            }}
          />
          Registered for GST
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          {draft.gstRegistered ? (
            <div className="flex flex-col gap-1.5">
              <TextField
                id={id("gstin")}
                label="GSTIN"
                value={draft.gstin}
                error={problems.gstin}
                mono
                onChange={(value) => {
                  set("gstin", value);
                }}
              />
              {gstinCheck !== undefined && GSTIN_PATTERN.test(gstin) ? gstinCheck(gstin) : null}
            </div>
          ) : null}
          <TextField
            id={id("pan")}
            label="PAN"
            value={draft.pan}
            error={problems.pan}
            mono
            onChange={(value) => {
              set("pan", value);
            }}
          />
          <TextField
            id={id("years")}
            label="Years in business"
            optional
            inputMode="numeric"
            value={draft.yearsInBusiness}
            error={problems.years_in_business}
            onChange={(value) => {
              set("yearsInBusiness", value);
            }}
          />
          <TextField
            id={id("brands")}
            label="Brands sold now"
            optional
            value={draft.currentBrands}
            error={problems.current_brands}
            onChange={(value) => {
              set("currentBrands", value);
            }}
          />
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">Address</legend>
        <TextArea
          id={id("address")}
          label="Shop address"
          value={draft.address}
          error={problems.address}
          onChange={(value) => {
            set("address", value);
          }}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={id("pincode")}
            label="Pincode"
            inputMode="numeric"
            value={draft.pincode}
            error={problems.pincode}
            onChange={(value) => {
              set("pincode", value);
            }}
          />
          <TextField
            id={id("email")}
            label="Email"
            optional
            inputMode="email"
            value={draft.email}
            error={problems.email}
            onChange={(value) => {
              set("email", value);
            }}
          />
        </div>
        <TextArea
          id={id("godown")}
          label="Godown address"
          optional
          value={draft.godownAddress}
          error={problems.godown_address}
          onChange={(value) => {
            set("godownAddress", value);
          }}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-semibold text-foreground">Bank</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={id("bank-name")}
            label="Account name"
            value={draft.bankAccountName}
            error={problems.bank_account_name}
            onChange={(value) => {
              set("bankAccountName", value);
            }}
          />
          <TextField
            id={id("bank-no")}
            label="Account number"
            inputMode="numeric"
            mono
            value={draft.bankAccountNo}
            error={problems.bank_account_no}
            placeholder={maskedAccount === null ? undefined : `${maskedAccount}: type to replace`}
            onChange={(value) => {
              set("bankAccountNo", value);
            }}
          />
          <TextField
            id={id("ifsc")}
            label="IFSC"
            mono
            value={draft.bankIfsc}
            error={problems.bank_ifsc}
            onChange={(value) => {
              set("bankIfsc", value);
            }}
          />
        </div>
      </fieldset>

      <TextArea
        id={id("notes")}
        label="Notes"
        optional
        value={draft.notes}
        error={problems.notes}
        onChange={(value) => {
          set("notes", value);
        }}
      />
    </div>
  );
}

function TextField({
  id,
  label,
  value,
  error,
  optional = false,
  mono = false,
  inputMode,
  placeholder,
  description,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  optional?: boolean;
  mono?: boolean;
  inputMode?: "numeric" | "email";
  placeholder?: string | undefined;
  description?: string;
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy = error !== undefined ? `${id}-error` : description ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <Input
        id={id}
        value={value}
        inputMode={inputMode}
        placeholder={placeholder}
        autoComplete="off"
        className={mono ? "font-mono" : undefined}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {description !== undefined && error === undefined ? (
        <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}

function TextArea({
  id,
  label,
  value,
  error,
  optional = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  optional?: boolean;
  onChange: (next: string) => void;
}): React.JSX.Element {
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <Textarea
        id={id}
        rows={2}
        maxLength={500}
        value={value}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={error === undefined ? undefined : `${id}-error`}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
