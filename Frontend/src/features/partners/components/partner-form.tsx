"use client";

import type * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import {
  PARTNER_TYPES,
  type CreatePartnerRequest,
  type Partner,
  type PartnerType,
  type PatchPartnerRequest,
} from "@/features/partners/api/partners.schemas";
import { PARTNER_TYPE_LABELS, parentTypeOf } from "@/features/partners/lib/partner-labels";
import { normalizeIndianMobile } from "@/lib/format";

import { ParentPicker, type ParentChoice } from "./parent-picker";

/** The backend's shapes (migration 004), checked here first so the form names the field. */
const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MONEY_PATTERN = /^\d+(\.\d{1,2})?$/;
const CODE_MAX = 32;
const TERMS_MAX = 365;

/** What the form holds, as typed. */
export interface PartnerDraft {
  readonly type: PartnerType;
  readonly parent: ParentChoice | null;
  readonly code: string;
  readonly name: string;
  readonly territory: TerritoryChoice | null;
  readonly contactName: string;
  readonly mobile: string;
  readonly email: string;
  readonly address: string;
  readonly gstin: string;
  readonly pan: string;
  readonly gstRegistered: boolean;
  readonly creditLimit: string;
  readonly paymentTermsDays: string;
}

export function emptyPartnerDraft(type: PartnerType = "distributor"): PartnerDraft {
  return {
    type,
    parent: null,
    code: "",
    name: "",
    territory: null,
    contactName: "",
    mobile: "",
    email: "",
    address: "",
    gstin: "",
    pan: "",
    gstRegistered: false,
    creditLimit: "",
    paymentTermsDays: "",
  };
}

export function draftOfPartner(partner: Partner): PartnerDraft {
  return {
    type: partner.type,
    parent: partner.parent === null ? null : { id: partner.parent.id, name: partner.parent.name },
    code: partner.code,
    name: partner.name,
    territory: partner.territory,
    contactName: partner.contactName ?? "",
    mobile: partner.mobile === null ? "" : `+${partner.mobile}`,
    email: partner.email ?? "",
    address: partner.address ?? "",
    gstin: partner.gstin ?? "",
    pan: partner.pan ?? "",
    gstRegistered: partner.gstRegistered,
    creditLimit: partner.creditLimit ?? "",
    paymentTermsDays: partner.paymentTermsDays === null ? "" : String(partner.paymentTermsDays),
  };
}

/** The form's field names, as a refusal's `fields` keys map onto them. */
export type PartnerField = keyof PartnerDraft | "form";

const WIRE_FIELDS: Readonly<Record<string, PartnerField>> = {
  partner_type: "type",
  parent_id: "parent",
  code: "code",
  name: "name",
  territory_id: "territory",
  contact_name: "contactName",
  mobile: "mobile",
  email: "email",
  address: "address",
  gstin: "gstin",
  pan: "pan",
  is_gst_registered: "gstRegistered",
  credit_limit: "creditLimit",
  payment_terms_days: "paymentTermsDays",
};

/** A 422's `fields` as the form's: anything it doesn't know (`body`, `id`) goes on top. */
export function partnerFieldsOf(
  fields: Readonly<Record<string, string>>,
): Partial<Record<PartnerField, string>> {
  const out: Partial<Record<PartnerField, string>> = {};
  for (const [path, message] of Object.entries(fields)) {
    const field = WIRE_FIELDS[path] ?? "form";
    const text = `${message.charAt(0).toUpperCase()}${message.slice(1)}${/[.!?]$/.test(message) ? "" : "."}`;
    out[field] = out[field] === undefined ? text : `${out[field]} ${text}`;
  }
  return out;
}

const upper = (value: string): string => value.trim().toUpperCase().replace(/\s+/g, "");

/** What the form would refuse before sending, field by field. */
export function partnerDraftProblems(
  draft: PartnerDraft,
  mode: "create" | "edit",
): Partial<Record<PartnerField, string>> {
  const problems: Partial<Record<PartnerField, string>> = {};
  const parentType = parentTypeOf(draft.type);
  if (mode === "create") {
    if (draft.code.trim() === "") problems.code = "Enter the partner's code.";
    else if (draft.code.trim().length > CODE_MAX)
      problems.code = `At most ${String(CODE_MAX)} characters.`;
    if (parentType !== null && draft.parent === null) {
      problems.parent = `Choose the ${PARTNER_TYPE_LABELS[parentType].toLowerCase()} it sits under.`;
    }
  }
  if (draft.name.trim() === "") problems.name = "Enter the business name.";
  if (draft.territory === null) problems.territory = "Choose where it works.";
  const mobile = draft.mobile.trim();
  if (mobile !== "" && normalizeIndianMobile(mobile) === null) {
    problems.mobile = "Enter a 10-digit Indian mobile number, or leave it empty.";
  }
  if (draft.email.trim() !== "" && !EMAIL_PATTERN.test(draft.email.trim())) {
    problems.email = "Enter a valid email address, or leave it empty.";
  }
  const gstin = upper(draft.gstin);
  if (gstin !== "" && !GSTIN_PATTERN.test(gstin)) {
    problems.gstin = "A GSTIN is 15 characters, like 24ABCDE1234F1Z5.";
  } else if (gstin === "" && draft.gstRegistered) {
    problems.gstin = "Enter the GSTIN of a GST-registered partner.";
  }
  const pan = upper(draft.pan);
  if (pan !== "" && !PAN_PATTERN.test(pan))
    problems.pan = "A PAN is 10 characters, like ABCDE1234F.";
  const credit = draft.creditLimit.trim().replace(/,/g, "");
  if (credit !== "" && !MONEY_PATTERN.test(credit)) {
    problems.creditLimit = "Rupees, 0 or more, with at most two decimals.";
  }
  const terms = draft.paymentTermsDays.trim();
  if (terms !== "" && (!/^\d+$/.test(terms) || Number(terms) > TERMS_MAX)) {
    problems.paymentTermsDays = `Whole days, 0 to ${String(TERMS_MAX)}.`;
  }
  return problems;
}

const orNull = (value: string): string | null => (value.trim() === "" ? null : value.trim());

function moneyOf(value: string): string | null {
  const credit = value.trim().replace(/,/g, "");
  return credit === "" ? null : Number(credit).toFixed(2);
}

function daysOf(value: string): number | null {
  return value.trim() === "" ? null : Number(value.trim());
}

/** POST /partners from a complete draft (call only when `partnerDraftProblems` is empty). */
export function createPartnerRequestOf(draft: PartnerDraft, staff: boolean): CreatePartnerRequest {
  const mobile = orNull(draft.mobile);
  return {
    parent_id: parentTypeOf(draft.type) === null ? null : (draft.parent?.id ?? null),
    partner_type: draft.type,
    code: draft.code.trim(),
    name: draft.name.trim(),
    territory_id: draft.territory?.id ?? "",
    contact_name: orNull(draft.contactName),
    mobile: mobile === null ? null : (normalizeIndianMobile(mobile) ?? mobile),
    email: orNull(draft.email)?.toLowerCase() ?? null,
    address: orNull(draft.address),
    gstin: orNull(upper(draft.gstin)),
    pan: orNull(upper(draft.pan)),
    is_gst_registered: draft.gstRegistered,
    // Credit terms are staff only: a partner adding its own dealer sends none.
    credit_limit: staff ? moneyOf(draft.creditLimit) : null,
    payment_terms_days: staff ? daysOf(draft.paymentTermsDays) : null,
  };
}

/** PATCH /partners/{id}: only what changed. A cleared optional field is sent as null. */
export function patchPartnerRequestOf(
  draft: PartnerDraft,
  partner: Partner,
  staff: boolean,
): PatchPartnerRequest {
  const before = draftOfPartner(partner);
  const changed = (key: "contactName" | "email" | "address"): boolean =>
    draft[key].trim() !== before[key].trim();
  const mobile = orNull(draft.mobile);
  const mobileWire = mobile === null ? null : (normalizeIndianMobile(mobile) ?? mobile);
  const beforeMobile = partner.mobile === null ? null : `+${partner.mobile}`;
  return {
    ...(draft.name.trim() === partner.name ? {} : { name: draft.name.trim() }),
    ...(changed("contactName") ? { contact_name: orNull(draft.contactName) } : {}),
    ...(mobileWire === beforeMobile ? {} : { mobile: mobileWire }),
    ...(changed("email") ? { email: orNull(draft.email)?.toLowerCase() ?? null } : {}),
    ...(changed("address") ? { address: orNull(draft.address) } : {}),
    ...(upper(draft.gstin) === upper(before.gstin) ? {} : { gstin: orNull(upper(draft.gstin)) }),
    ...(upper(draft.pan) === upper(before.pan) ? {} : { pan: orNull(upper(draft.pan)) }),
    ...(draft.gstRegistered === partner.gstRegistered
      ? {}
      : { is_gst_registered: draft.gstRegistered }),
    ...(staff && draft.territory !== null && draft.territory.id !== partner.territory?.id
      ? { territory_id: draft.territory.id }
      : {}),
    ...(staff && moneyOf(draft.creditLimit) !== moneyOf(partner.creditLimit ?? "")
      ? { credit_limit: moneyOf(draft.creditLimit) }
      : {}),
    ...(staff && daysOf(draft.paymentTermsDays) !== partner.paymentTermsDays
      ? { payment_terms_days: daysOf(draft.paymentTermsDays) }
      : {}),
  };
}

/**
 * CHNL-002, CHNL-003 · A partner's form. Creating, choose the type first: a distributor sits
 * at the top, a dealer under a distributor and a sub-dealer under a dealer, so the form asks
 * for the partner one type up. The type, the parent and the code never change after; the
 * territory and credit terms are staff's to set.
 */
export function PartnerFields({
  mode,
  draft,
  onChange,
  errors,
  staff,
}: {
  mode: "create" | "edit";
  draft: PartnerDraft;
  onChange: (next: PartnerDraft) => void;
  errors: Partial<Record<PartnerField, string>>;
  staff: boolean;
}): React.JSX.Element {
  const set = (patch: Partial<PartnerDraft>): void => {
    onChange({ ...draft, ...patch });
  };
  const invalid = (field: PartnerField): true | undefined =>
    errors[field] === undefined ? undefined : true;
  const describe = (field: PartnerField, help?: string): string | undefined =>
    errors[field] === undefined ? help : `partner-${field}-error`;
  const parentType = parentTypeOf(draft.type);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle level={2}>Where it sits</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {mode === "create" ? (
            <Field className="sm:col-span-2" data-invalid={invalid("type")}>
              <FieldLabel id="partner-type-label">Type</FieldLabel>
              <ToggleGroup
                aria-labelledby="partner-type-label"
                value={[draft.type]}
                onValueChange={(next) => {
                  const chosen = PARTNER_TYPES.find((type) => type === next[0]);
                  if (chosen !== undefined && chosen !== draft.type) {
                    set({ type: chosen, parent: null });
                  }
                }}
                className="w-full sm:w-auto"
              >
                {PARTNER_TYPES.map((type) => (
                  <ToggleGroupItem key={type} value={type} className="flex-1 sm:flex-none">
                    {PARTNER_TYPE_LABELS[type]}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              <FieldDescription>
                Its prices come from the {PARTNER_TYPE_LABELS[draft.type].toLowerCase()} tier. The
                type can&apos;t change once it&apos;s added.
              </FieldDescription>
              <FieldError id="partner-type-error">{errors.type}</FieldError>
            </Field>
          ) : null}

          {parentType === null ? null : (
            <Field data-invalid={invalid("parent")}>
              <FieldLabel htmlFor="partner-parent">
                Under which {PARTNER_TYPE_LABELS[parentType].toLowerCase()}
              </FieldLabel>
              {mode === "create" ? (
                <ParentPicker
                  id="partner-parent"
                  type={parentType}
                  value={draft.parent}
                  onValueChange={(parent) => {
                    set({ parent });
                  }}
                  aria-invalid={invalid("parent")}
                  aria-describedby={describe("parent")}
                />
              ) : (
                <Input id="partner-parent" value={draft.parent?.name ?? ""} disabled readOnly />
              )}
              <FieldError id="partner-parent-error">{errors.parent}</FieldError>
            </Field>
          )}

          <Field data-invalid={invalid("territory")}>
            <FieldLabel htmlFor="partner-territory">Territory</FieldLabel>
            <TerritoryPicker
              id="partner-territory"
              value={draft.territory}
              disabled={mode === "edit" && !staff}
              placeholder="Search a state, district or taluka"
              onValueChange={(territory) => {
                set({ territory });
              }}
              aria-invalid={invalid("territory")}
              aria-describedby={describe("territory", "partner-territory-help")}
            />
            {errors.territory === undefined ? (
              <FieldDescription id="partner-territory-help">
                Where it works: staff over this area see it and its leads.
              </FieldDescription>
            ) : null}
            <FieldError id="partner-territory-error">{errors.territory}</FieldError>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle level={2}>Business</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={invalid("code")}>
            <FieldLabel htmlFor="partner-code">Code</FieldLabel>
            <Input
              id="partner-code"
              autoComplete="off"
              spellCheck={false}
              maxLength={CODE_MAX}
              value={draft.code}
              disabled={mode === "edit"}
              readOnly={mode === "edit"}
              aria-invalid={invalid("code")}
              aria-describedby={describe("code", "partner-code-help")}
              onChange={(event) => {
                set({ code: event.target.value });
              }}
            />
            {errors.code === undefined ? (
              <FieldDescription id="partner-code-help">
                {mode === "create"
                  ? "Unique across every partner; leads and orders show it."
                  : "The code never changes."}
              </FieldDescription>
            ) : null}
            <FieldError id="partner-code-error">{errors.code}</FieldError>
          </Field>

          <Field data-invalid={invalid("name")}>
            <FieldLabel htmlFor="partner-name">Business name</FieldLabel>
            <Input
              id="partner-name"
              autoComplete="organization"
              maxLength={200}
              value={draft.name}
              aria-invalid={invalid("name")}
              aria-describedby={describe("name")}
              onChange={(event) => {
                set({ name: event.target.value });
              }}
            />
            <FieldError id="partner-name-error">{errors.name}</FieldError>
          </Field>

          <Field data-invalid={invalid("gstin")}>
            <FieldLabel htmlFor="partner-gstin">GSTIN (optional)</FieldLabel>
            <Input
              id="partner-gstin"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={15}
              className="font-mono uppercase"
              value={draft.gstin}
              aria-invalid={invalid("gstin")}
              aria-describedby={describe("gstin")}
              onChange={(event) => {
                set({ gstin: event.target.value });
              }}
            />
            <FieldError id="partner-gstin-error">{errors.gstin}</FieldError>
          </Field>

          <Field data-invalid={invalid("pan")}>
            <FieldLabel htmlFor="partner-pan">PAN (optional)</FieldLabel>
            <Input
              id="partner-pan"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={10}
              className="font-mono uppercase"
              value={draft.pan}
              aria-invalid={invalid("pan")}
              aria-describedby={describe("pan")}
              onChange={(event) => {
                set({ pan: event.target.value });
              }}
            />
            <FieldError id="partner-pan-error">{errors.pan}</FieldError>
          </Field>

          <div className="flex items-start gap-2 sm:col-span-2">
            <Checkbox
              id="partner-gst-registered"
              checked={draft.gstRegistered}
              aria-invalid={invalid("gstRegistered")}
              onCheckedChange={(checked) => {
                set({ gstRegistered: checked });
              }}
            />
            <Label htmlFor="partner-gst-registered" className="flex flex-col items-start gap-0.5">
              <span className="text-sm">Registered for GST</span>
              <span className="text-xs font-normal text-muted-foreground">
                A registered partner needs its GSTIN.
              </span>
            </Label>
          </div>
          {errors.gstRegistered === undefined ? null : (
            <p role="alert" className="text-sm text-danger sm:col-span-2">
              {errors.gstRegistered}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle level={2}>Contact</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={invalid("contactName")}>
            <FieldLabel htmlFor="partner-contact">Contact person (optional)</FieldLabel>
            <Input
              id="partner-contact"
              autoComplete="off"
              maxLength={200}
              value={draft.contactName}
              aria-invalid={invalid("contactName")}
              aria-describedby={describe("contactName")}
              onChange={(event) => {
                set({ contactName: event.target.value });
              }}
            />
            <FieldError id="partner-contactName-error">{errors.contactName}</FieldError>
          </Field>

          <Field data-invalid={invalid("mobile")}>
            <FieldLabel htmlFor="partner-mobile">Mobile (optional)</FieldLabel>
            <Input
              id="partner-mobile"
              type="tel"
              inputMode="tel"
              autoComplete="off"
              value={draft.mobile}
              aria-invalid={invalid("mobile")}
              aria-describedby={describe("mobile")}
              onChange={(event) => {
                set({ mobile: event.target.value });
              }}
            />
            <FieldError id="partner-mobile-error">{errors.mobile}</FieldError>
          </Field>

          <Field data-invalid={invalid("email")}>
            <FieldLabel htmlFor="partner-email">Email (optional)</FieldLabel>
            <Input
              id="partner-email"
              type="email"
              inputMode="email"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={254}
              value={draft.email}
              aria-invalid={invalid("email")}
              aria-describedby={describe("email")}
              onChange={(event) => {
                set({ email: event.target.value });
              }}
            />
            <FieldError id="partner-email-error">{errors.email}</FieldError>
          </Field>

          <Field data-invalid={invalid("address")} className="sm:col-span-2">
            <FieldLabel htmlFor="partner-address">Address (optional)</FieldLabel>
            <Textarea
              id="partner-address"
              rows={3}
              maxLength={1000}
              value={draft.address}
              aria-invalid={invalid("address")}
              aria-describedby={describe("address")}
              onChange={(event) => {
                set({ address: event.target.value });
              }}
            />
            <FieldError id="partner-address-error">{errors.address}</FieldError>
          </Field>
        </CardContent>
      </Card>

      {staff ? (
        <Card>
          <CardHeader>
            <CardTitle level={2}>Credit terms</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field data-invalid={invalid("creditLimit")}>
              <FieldLabel htmlFor="partner-credit">Credit limit in ₹ (optional)</FieldLabel>
              <Input
                id="partner-credit"
                inputMode="decimal"
                autoComplete="off"
                className="tabular-nums"
                value={draft.creditLimit}
                aria-invalid={invalid("creditLimit")}
                aria-describedby={describe("creditLimit", "partner-credit-help")}
                onChange={(event) => {
                  set({ creditLimit: event.target.value });
                }}
              />
              {errors.creditLimit === undefined ? (
                <FieldDescription id="partner-credit-help">
                  Recorded for reference; orders aren&apos;t stopped at it yet.
                </FieldDescription>
              ) : null}
              <FieldError id="partner-creditLimit-error">{errors.creditLimit}</FieldError>
            </Field>

            <Field data-invalid={invalid("paymentTermsDays")}>
              <FieldLabel htmlFor="partner-terms">Payment terms in days (optional)</FieldLabel>
              <Input
                id="partner-terms"
                inputMode="numeric"
                autoComplete="off"
                className="tabular-nums"
                value={draft.paymentTermsDays}
                aria-invalid={invalid("paymentTermsDays")}
                aria-describedby={describe("paymentTermsDays")}
                onChange={(event) => {
                  set({ paymentTermsDays: event.target.value });
                }}
              />
              <FieldError id="partner-paymentTermsDays-error">{errors.paymentTermsDays}</FieldError>
            </Field>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
