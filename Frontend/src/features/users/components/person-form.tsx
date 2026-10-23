"use client";

import { Cancel01Icon, RefreshIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { DealerPicker, type DealerChoice } from "@/features/complaints/components/dealer-picker";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { roleListQueryOptions } from "@/features/users/api/users.queries";
import {
  USER_TYPES,
  type CreateUserRequest,
  type PatchUserRequest,
  type UserDetail,
  type UserType,
} from "@/features/users/api/users.schemas";
import { generateTemporaryPassword } from "@/features/users/lib/temporary-password";
import { USER_TYPE_LABELS } from "@/features/users/lib/user-labels";
import { normalizeIndianMobile } from "@/lib/format";

import { OfficePicker, type OfficeValue } from "./office-picker";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PASSWORD_MIN = 12;

/** What the form holds, as typed. */
export interface PersonDraft {
  readonly userType: UserType;
  readonly name: string;
  readonly email: string;
  readonly mobile: string;
  readonly role: string | null;
  readonly office: OfficeValue | null;
  readonly territories: readonly TerritoryChoice[];
  readonly partner: DealerChoice | null;
  readonly password: string;
}

export function emptyDraft(): PersonDraft {
  return {
    userType: "staff",
    name: "",
    email: "",
    mobile: "",
    role: null,
    office: null,
    territories: [],
    partner: null,
    password: generateTemporaryPassword(),
  };
}

export function draftOf(user: UserDetail): PersonDraft {
  return {
    userType: user.userType,
    name: user.name,
    email: user.email ?? "",
    mobile: user.mobile === null ? "" : `+${user.mobile}`,
    role: user.role?.code ?? null,
    office: user.office,
    territories: user.territories,
    partner:
      user.partner === null
        ? null
        : { id: user.partner.id, name: user.partner.name ?? "A partner" },
    password: "",
  };
}

/** The form's field names, as a refusal's `fields` keys map onto them. */
export type PersonField =
  | "userType"
  | "name"
  | "email"
  | "mobile"
  | "role"
  | "office"
  | "territories"
  | "partner"
  | "password"
  | "form";

const WIRE_FIELDS: Readonly<Record<string, PersonField>> = {
  user_type: "userType",
  full_name: "name",
  email: "email",
  mobile: "mobile",
  role: "role",
  org_unit_id: "office",
  territory_ids: "territories",
  partner_id: "partner",
  password: "password",
};

/** A 422's `fields` as the form's: unknown keys (the last administrator's `id`) go on top. */
export function formFieldsOf(
  fields: Readonly<Record<string, string>>,
): Partial<Record<PersonField, string>> {
  const out: Partial<Record<PersonField, string>> = {};
  for (const [path, message] of Object.entries(fields)) {
    const field = WIRE_FIELDS[path] ?? "form";
    const text = `${message.charAt(0).toUpperCase()}${message.slice(1)}${/[.!?]$/.test(message) ? "" : "."}`;
    out[field] = out[field] === undefined ? text : `${out[field]} ${text}`;
  }
  return out;
}

/** What the form would refuse before sending, field by field. */
export function draftProblems(
  draft: PersonDraft,
  mode: "create" | "edit",
): Partial<Record<PersonField, string>> {
  const problems: Partial<Record<PersonField, string>> = {};
  if (draft.name.trim() === "") problems.name = "Enter their full name.";
  const mobile = draft.mobile.trim();
  if (draft.userType === "staff") {
    if (draft.email.trim() === "") problems.email = "Enter their work email.";
    else if (!EMAIL_PATTERN.test(draft.email.trim()))
      problems.email = "Enter a valid email address.";
    if (mobile !== "" && normalizeIndianMobile(mobile) === null) {
      problems.mobile = "Enter a 10-digit Indian mobile number, or leave it empty.";
    }
    if (draft.role === null) problems.role = "Choose their role.";
    if (draft.office === null) problems.office = "Choose their office.";
    if (mode === "create" && draft.password.length < PASSWORD_MIN) {
      problems.password = `At least ${String(PASSWORD_MIN)} characters.`;
    }
  } else {
    if (mobile === "") problems.mobile = "Enter the mobile they'll sign in with.";
    else if (normalizeIndianMobile(mobile) === null) {
      problems.mobile = "Enter a 10-digit Indian mobile number.";
    }
    if (draft.partner === null) problems.partner = "Choose their partner.";
  }
  return problems;
}

/** POST /users from a complete draft (call only when `draftProblems` is empty). */
export function createRequestOf(draft: PersonDraft): CreateUserRequest {
  const mobile = normalizeIndianMobile(draft.mobile.trim());
  if (draft.userType === "partner_user") {
    return {
      user_type: "partner_user",
      full_name: draft.name.trim(),
      mobile: mobile ?? draft.mobile.trim(),
      partner_id: draft.partner?.id ?? "",
    };
  }
  return {
    user_type: "staff",
    full_name: draft.name.trim(),
    email: draft.email.trim().toLowerCase(),
    mobile,
    role: draft.role ?? "",
    org_unit_id: draft.office?.id ?? "",
    territory_ids: draft.territories.map((territory) => territory.id),
    password: draft.password,
  };
}

/** PATCH /users/{id}: only what changed. Your own role, office and territories never change. */
export function patchRequestOf(
  draft: PersonDraft,
  user: UserDetail,
  isSelf: boolean,
): PatchUserRequest {
  const before = draftOf(user);
  const mobile = normalizeIndianMobile(draft.mobile.trim());
  const sameTerritories =
    before.territories.length === draft.territories.length &&
    before.territories.every((territory) =>
      draft.territories.some((item) => item.id === territory.id),
    );
  return {
    ...(draft.name.trim() === user.name ? {} : { full_name: draft.name.trim() }),
    ...(user.userType === "staff" && draft.email.trim().toLowerCase() !== (user.email ?? "")
      ? { email: draft.email.trim().toLowerCase() }
      : {}),
    ...(mobile !== null && mobile !== before.mobile ? { mobile } : {}),
    ...(isSelf
      ? {}
      : {
          ...(user.userType === "staff" && draft.role !== null && draft.role !== before.role
            ? { role: draft.role }
            : {}),
          ...(user.userType === "staff" &&
          draft.office !== null &&
          draft.office.id !== before.office?.id
            ? { org_unit_id: draft.office.id }
            : {}),
          ...(user.userType === "staff" && !sameTerritories
            ? { territory_ids: draft.territories.map((territory) => territory.id) }
            : {}),
          ...(user.userType === "partner_user" &&
          draft.partner !== null &&
          draft.partner.id !== before.partner?.id
            ? { partner_id: draft.partner.id }
            : {}),
        }),
  };
}

/**
 * ADMN-003, ADMN-004 · A person's form. Creating, choose staff or partner user first: staff
 * get an email, a staff role, an office, the territories they read and a temporary password;
 * a partner user gets a mobile and a partner, their role following the partner's type.
 * Editing your own row, only your details can change.
 */
export function PersonFields({
  mode,
  draft,
  onChange,
  errors,
  isSelf = false,
}: {
  mode: "create" | "edit";
  draft: PersonDraft;
  onChange: (next: PersonDraft) => void;
  errors: Partial<Record<PersonField, string>>;
  isSelf?: boolean;
}): React.JSX.Element {
  const roles = useQuery(roleListQueryOptions());
  const staffRoles = (roles.data ?? []).filter((role) => !role.portal);
  const roleItems = staffRoles.map((role) => ({ value: role.code, label: role.name }));
  const [adding, setAdding] = useState<TerritoryChoice | null>(null);
  const staff = draft.userType === "staff";
  const set = (patch: Partial<PersonDraft>): void => {
    onChange({ ...draft, ...patch });
  };
  const invalid = (field: PersonField): true | undefined =>
    errors[field] === undefined ? undefined : true;
  const describe = (field: PersonField, help?: string): string | undefined =>
    errors[field] === undefined ? help : `person-${field}-error`;

  return (
    <div className="flex flex-col gap-4">
      {mode === "create" ? (
        <Field>
          <FieldLabel id="person-type-label">Who are you adding?</FieldLabel>
          <ToggleGroup
            aria-labelledby="person-type-label"
            value={[draft.userType]}
            onValueChange={(next) => {
              const chosen = USER_TYPES.find((type) => type === next[0]);
              if (chosen !== undefined) set({ userType: chosen });
            }}
            className="w-full sm:w-auto"
          >
            {USER_TYPES.map((type) => (
              <ToggleGroupItem key={type} value={type} className="flex-1 sm:flex-none">
                {type === "staff" ? "Polysil staff" : "Partner user"}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <FieldDescription>
            {staff
              ? "Signs in with a work email and a password; you give them a temporary one."
              : "A dealer's or distributor's person; signs in with a code sent to their mobile."}
          </FieldDescription>
        </Field>
      ) : (
        <p className="text-sm text-muted-foreground">{USER_TYPE_LABELS[draft.userType]}</p>
      )}

      <Card>
        <CardContent className="grid gap-4 pt-4 sm:grid-cols-2">
          <Field data-invalid={invalid("name")}>
            <FieldLabel htmlFor="person-name">Full name</FieldLabel>
            <Input
              id="person-name"
              autoComplete="off"
              maxLength={200}
              value={draft.name}
              aria-invalid={invalid("name")}
              aria-describedby={describe("name")}
              onChange={(event) => {
                set({ name: event.target.value });
              }}
            />
            <FieldError id="person-name-error">{errors.name}</FieldError>
          </Field>

          {staff ? (
            <Field data-invalid={invalid("email")}>
              <FieldLabel htmlFor="person-email">Work email</FieldLabel>
              <Input
                id="person-email"
                type="email"
                inputMode="email"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                value={draft.email}
                aria-invalid={invalid("email")}
                aria-describedby={describe("email", "person-email-help")}
                onChange={(event) => {
                  set({ email: event.target.value });
                }}
              />
              {errors.email === undefined ? (
                <FieldDescription id="person-email-help">They sign in with it.</FieldDescription>
              ) : null}
              <FieldError id="person-email-error">{errors.email}</FieldError>
            </Field>
          ) : null}

          <Field data-invalid={invalid("mobile")}>
            <FieldLabel htmlFor="person-mobile">
              {staff ? "Mobile (optional)" : "Mobile"}
            </FieldLabel>
            <Input
              id="person-mobile"
              type="tel"
              inputMode="tel"
              autoComplete="off"
              value={draft.mobile}
              aria-invalid={invalid("mobile")}
              aria-describedby={describe("mobile", staff ? undefined : "person-mobile-help")}
              onChange={(event) => {
                set({ mobile: event.target.value });
              }}
            />
            {staff || errors.mobile !== undefined ? null : (
              <FieldDescription id="person-mobile-help">
                Their sign-in code comes here on WhatsApp.
              </FieldDescription>
            )}
            <FieldError id="person-mobile-error">{errors.mobile}</FieldError>
          </Field>

          {staff ? (
            <>
              <Field data-invalid={invalid("role")}>
                <FieldLabel htmlFor="person-role">Role</FieldLabel>
                <Select
                  items={roleItems}
                  value={draft.role}
                  disabled={isSelf}
                  onValueChange={(next) => {
                    set({ role: typeof next === "string" ? next : null });
                  }}
                >
                  <SelectTrigger
                    id="person-role"
                    className="w-full"
                    aria-invalid={invalid("role")}
                    aria-describedby={describe("role", isSelf ? "person-self-help" : undefined)}
                  >
                    <SelectValue
                      placeholder={roles.isPending ? "Loading roles…" : "Choose a role"}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {roleItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError id="person-role-error">{errors.role}</FieldError>
              </Field>

              <Field data-invalid={invalid("office")}>
                <FieldLabel htmlFor="person-office">Office</FieldLabel>
                {isSelf ? (
                  <Input id="person-office" value={draft.office?.name ?? ""} disabled readOnly />
                ) : (
                  <OfficePicker
                    id="person-office"
                    value={draft.office}
                    onValueChange={(office) => {
                      set({ office });
                    }}
                    invalid={errors.office !== undefined}
                    {...(errors.office === undefined ? {} : { describedBy: "person-office-error" })}
                  />
                )}
                <FieldError id="person-office-error">{errors.office}</FieldError>
              </Field>

              <Field data-invalid={invalid("territories")} className="sm:col-span-2">
                <FieldLabel htmlFor="person-territory">Territories</FieldLabel>
                {draft.territories.length === 0 ? null : (
                  <ul aria-label="Chosen territories" className="flex flex-wrap gap-1.5">
                    {draft.territories.map((territory) => (
                      <li key={territory.id}>
                        <Badge variant="neutral" className="gap-1 pr-1">
                          {territory.name}
                          {isSelf ? null : (
                            <button
                              type="button"
                              aria-label={`Remove ${territory.name}`}
                              className="rounded-full p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                              onClick={() => {
                                set({
                                  territories: draft.territories.filter(
                                    (item) => item.id !== territory.id,
                                  ),
                                });
                              }}
                            >
                              <Icon icon={Cancel01Icon} size="sm" />
                            </button>
                          )}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
                {isSelf ? null : (
                  <TerritoryPicker
                    id="person-territory"
                    value={adding}
                    levels={["state", "district", "taluka"]}
                    placeholder="Add a state, district or taluka"
                    onValueChange={(territory) => {
                      setAdding(null);
                      if (territory === null) return;
                      if (draft.territories.some((item) => item.id === territory.id)) return;
                      set({ territories: [...draft.territories, territory] });
                    }}
                    aria-invalid={invalid("territories")}
                    aria-describedby={describe("territories", "person-territory-help")}
                  />
                )}
                {errors.territories === undefined ? (
                  <FieldDescription id="person-territory-help">
                    What they see where their role reads by territory, such as leads. A field or
                    district role needs at least one.
                  </FieldDescription>
                ) : null}
                <FieldError id="person-territories-error">{errors.territories}</FieldError>
              </Field>
            </>
          ) : (
            <Field data-invalid={invalid("partner")}>
              <FieldLabel htmlFor="person-partner">Partner</FieldLabel>
              {isSelf ? (
                <Input id="person-partner" value={draft.partner?.name ?? ""} disabled readOnly />
              ) : (
                <DealerPicker
                  id="person-partner"
                  value={draft.partner}
                  onValueChange={(partner) => {
                    set({ partner });
                  }}
                />
              )}
              <FieldDescription>
                Their role follows the partner: dealer, distributor…
              </FieldDescription>
              <FieldError id="person-partner-error">{errors.partner}</FieldError>
            </Field>
          )}

          {isSelf ? (
            <p id="person-self-help" className="text-xs text-muted-foreground sm:col-span-2">
              This is you: another administrator changes your role, office and territories.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {staff && mode === "create" ? (
        <Card>
          <CardContent className="pt-4">
            <Field data-invalid={invalid("password")}>
              <FieldLabel htmlFor="person-password">Temporary password</FieldLabel>
              <div className="flex gap-2">
                <Input
                  id="person-password"
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono"
                  value={draft.password}
                  aria-invalid={invalid("password")}
                  aria-describedby={describe("password", "person-password-help")}
                  onChange={(event) => {
                    set({ password: event.target.value });
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  aria-label="Suggest another password"
                  onClick={() => {
                    set({ password: generateTemporaryPassword() });
                  }}
                >
                  <Icon icon={RefreshIcon} />
                </Button>
              </div>
              {errors.password === undefined ? (
                <FieldDescription id="person-password-help">
                  Suggested for you; at least {PASSWORD_MIN} characters. Tell them in person or by
                  phone. They choose their own at the first sign-in.
                </FieldDescription>
              ) : null}
              <FieldError id="person-password-error">{errors.password}</FieldError>
            </Field>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
