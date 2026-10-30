"use client";

import { Settings02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { GST_SLABS } from "@/features/products/api/products.schemas";
import { formatRate } from "@/features/quotations/lib/quotation-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { usePatchSettings } from "@/features/settings/api/settings.mutations";
import { settingsQueryOptions } from "@/features/settings/api/settings.queries";
import type { Setting, SettingsPatchRequest } from "@/features/settings/api/settings.schemas";
import { roleListQueryOptions } from "@/features/users/api/users.queries";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/settings/components/company-settings.tsx",
  dataId: "ADMN-007",
});

/**
 * Each setting the backend seeds today (`app_setting`, migrations 041 to 060): its title, the
 * section it sits in, its choices in words, and a note where the handover asks for one. A key
 * not listed here still renders from its kind, titled from its own name, under "Other".
 */
interface SettingCopy {
  title: string;
  section: SectionId;
  choices?: Readonly<Record<string, string>>;
  note?: string;
  /** Role codes kept in the order they were picked: an approval chain. */
  ordered?: boolean;
}

const SECTIONS = [
  { id: "orders", title: "Orders" },
  { id: "complaints", title: "Complaints" },
  { id: "dealers", title: "Dealers" },
  { id: "customers", title: "Customers" },
  { id: "other", title: "Other" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const OFF_ON: Readonly<Record<string, string>> = { off: "Off", on: "On" };

const COPY: Readonly<Record<string, SettingCopy>> = {
  order_amend_reapproval: {
    title: "Re-approving an amended order",
    section: "orders",
    choices: { always: "Always", value_rises: "Only when its value rises" },
  },
  sale_counted_at: {
    title: "When an order counts as a sale",
    section: "orders",
    choices: {
      submission: "When it's submitted",
      approval: "When it's approved",
      dispatch: "When its last line ships",
      payment: "When it's paid in full",
    },
    note: "Changing this recalculates reports and targets for every month.",
  },
  dealer_credit_check: {
    title: "A dealer's credit limit",
    section: "orders",
    choices: { off: "Ignore it", warn: "Warn the approvers", block: "Refuse the order" },
  },
  replacement_approval_roles: {
    title: "Who approves a replacement order",
    section: "orders",
    ordered: true,
  },
  export_tax_treatment: {
    title: "Tax on an export",
    section: "orders",
    choices: { lut: "Zero-rated under a LUT", igst: "IGST at each line's rate" },
  },
  sample_pricing: {
    title: "Pricing a sample order",
    section: "orders",
    choices: { free: "Free", charged: "Priced like a commercial order" },
  },
  sample_max_value: { title: "The largest sample order, in rupees", section: "orders" },
  gst_slab_choices: {
    title: "GST slabs an item or freight can be set to",
    section: "orders",
    note: "Commercial and industrial quotations and orders. Each item still offers its own HSN slab.",
  },
  complaint_reopen_days: { title: "Days to reopen a complaint", section: "complaints" },
  complaint_reopen_roles: { title: "Who may reopen a complaint", section: "complaints" },
  complaint_reopen_clock: {
    title: "A reopened complaint's clock",
    section: "complaints",
    choices: { restart: "Starts again", continue: "Carries on" },
  },
  complaint_reopen_max: { title: "Times a complaint can be reopened", section: "complaints" },
  complaint_escalation: {
    title: "A complaint that misses its target",
    section: "complaints",
    choices: { off: "Do nothing", bell: "Ring the bell" },
  },
  tasks_for_dealers: { title: "Tasks for dealers", section: "dealers", choices: OFF_ON },
  dealer_rating_window_days: { title: "Days a dealer's rating counts", section: "dealers" },
  dealer_rating_payment_days: {
    title: "Dealer rating: days to full payment",
    section: "dealers",
  },
  dealer_rating_order_value: {
    title: "Dealer rating: rupees ordered",
    section: "dealers",
  },
  consumer_portal: {
    title: "The farmers' portal",
    section: "customers",
    choices: OFF_ON,
    note: "On, every customer's number can be sent a WhatsApp sign-in code, and each code is paid for. Off signs every farmer out.",
  },
  portal_otp_hourly_cap: {
    title: "Sign-in codes to customers in an hour",
    section: "customers",
  },
};

function humanize(code: string): string {
  const text = code.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function settingTitle(key: string): string {
  return COPY[key]?.title ?? humanize(key);
}

function choiceLabel(key: string, value: string): string {
  return COPY[key]?.choices?.[value] ?? humanize(value);
}

function sectionOf(key: string): SectionId {
  return COPY[key]?.section ?? "other";
}

/** What a setting's editor holds: text for numbers, so a half-typed one isn't lost. */
type Draft = Readonly<Record<string, string | readonly string[]>>;

function draftOf(setting: Setting): string | readonly string[] {
  switch (setting.kind) {
    case "choice":
      return setting.value;
    case "int":
      return String(setting.value);
    case "roles":
      return setting.value;
    case "bands":
      return setting.value.map(String);
    case "slabs":
      return setting.value;
  }
}

function same(left: string | readonly string[], right: string | readonly string[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

/** Why a drafted value won't do, before the backend checks it again; null when it reads right. */
function problemOf(setting: Setting, draft: string | readonly string[]): string | null {
  if (setting.kind === "int") {
    const text = typeof draft === "string" ? draft.trim() : "";
    if (!/^\d+$/.test(text)) return "Enter a whole number.";
    const value = Number(text);
    if (setting.min !== null && value < setting.min) {
      return `At least ${formatNumber(setting.min)}.`;
    }
    if (setting.max !== null && value > setting.max) {
      return `At most ${formatNumber(setting.max)}.`;
    }
    return null;
  }
  if (setting.kind === "bands") {
    const values = Array.isArray(draft) ? draft.map((item) => item.trim()) : [];
    if (values.length !== 4 || values.some((item) => !/^\d+$/.test(item))) {
      return "Four whole numbers.";
    }
    const numbers = values.map(Number);
    if (numbers.some((value, index) => index > 0 && value <= (numbers[index - 1] ?? -1))) {
      return "Each one more than the one before.";
    }
  }
  if (setting.kind === "slabs" && (!Array.isArray(draft) || draft.length === 0)) {
    return "Choose at least one slab.";
  }
  return null;
}

/** The request value for a drafted one, typed for its kind. */
function requestValueOf(
  setting: Setting,
  draft: string | readonly string[],
): string | number | readonly string[] | readonly number[] {
  switch (setting.kind) {
    case "int":
      return Number(typeof draft === "string" ? draft.trim() : "0");
    case "bands":
      return (Array.isArray(draft) ? draft : []).map((item) => Number(String(item).trim()));
    case "roles":
      return Array.isArray(draft) ? draft : [];
    case "slabs":
      return [...(Array.isArray(draft) ? draft : [])].sort((a, b) => Number(a) - Number(b));
    case "choice":
      return typeof draft === "string" ? draft : "";
  }
}

/**
 * ADMN-007 · Admin → Company settings (FS-036): rules for orders, complaints, dealers and the
 * farmers' portal, in sections; more arrive with other features. Each setting is drawn from its
 * kind (a choice, a number in a range, roles, four rising bands, or GST slabs). Staff read them; those who
 * may edit masters change them and save them together.
 */
export function CompanySettings(): React.JSX.Element {
  const query = useQuery(settingsQueryOptions());
  return (
    <QueryView
      query={query}
      pending={<SettingsSkeleton />}
      isEmpty={(settings) => settings.length === 0}
      empty={
        <EmptyState
          icon={Settings02Icon}
          title="No settings yet"
          description="They arrive with the features that need them."
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(settings) => <SettingsForm key={settingsVersion(settings)} settings={settings} />}
    </QueryView>
  );
}

/** A new answer from the backend starts the form again from it. */
function settingsVersion(settings: readonly Setting[]): string {
  return settings.map((setting) => `${setting.key}@${setting.updatedAt}`).join("|");
}

function SettingsForm({ settings }: { settings: readonly Setting[] }): React.JSX.Element {
  const canEdit = useCan("masters", "edit");
  const patch = usePatchSettings();
  const initial: Draft = Object.fromEntries(settings.map((item) => [item.key, draftOf(item)]));
  const [draft, setDraft] = useState<Draft>(initial);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Readonly<Record<string, string>>>({});

  const changed = settings.filter((item) => !same(draft[item.key] ?? "", initial[item.key] ?? ""));
  const local: Record<string, string> = {};
  for (const item of changed) {
    const problem = problemOf(item, draft[item.key] ?? "");
    if (problem !== null) local[item.key] = problem;
  }
  const problems: Readonly<Record<string, string>> = { ...(shown ? local : {}), ...server };

  const save = useAsyncAction({
    action: () => {
      const body: SettingsPatchRequest = {
        values: Object.fromEntries(
          changed.map((item) => [item.key, requestValueOf(item, draft[item.key] ?? "")]),
        ),
      };
      return patch.mutateAsync(body);
    },
    logger: log,
    fn: "handleSaveSettings",
    dataId: "ADMN-007",
    onSuccess: () => {
      toast.success(changed.length === 1 ? "Setting saved" : "Settings saved");
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) {
        const mapped: Record<string, string> = {};
        for (const [path, message] of Object.entries(fields)) {
          mapped[path.replace(/^values\./, "")] = `The backend refused it: ${message}.`;
        }
        setServer(mapped);
        return;
      }
      toast.error("Settings not saved", { description: toUserFacingError(error).description });
    },
  });

  return (
    <form
      noValidate
      aria-label="Company settings"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        if (Object.keys(local).length > 0 || changed.length === 0) return;
        void save.run();
      }}
    >
      <p className="max-w-prose text-sm text-muted-foreground">
        Rules the whole company works by. Each says what it changes.
        {canEdit ? "" : " Only administrators of masters change them."}
      </p>
      {SECTIONS.map((section) => {
        const inSection = settings.filter((setting) => sectionOf(setting.key) === section.id);
        if (inSection.length === 0) return null;
        return (
          <section
            key={section.id}
            aria-labelledby={`settings-${section.id}`}
            className="flex flex-col gap-3"
          >
            <h2 id={`settings-${section.id}`} className="text-base font-semibold text-foreground">
              {section.title}
            </h2>
            {inSection.map((setting) => (
              <SettingCard
                key={setting.key}
                setting={setting}
                canEdit={canEdit}
                value={draft[setting.key] ?? draftOf(setting)}
                error={problems[setting.key]}
                onChange={(next) => {
                  setDraft((current) => ({ ...current, [setting.key]: next }));
                  setServer({});
                }}
              />
            ))}
          </section>
        );
      })}
      {canEdit ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            disabled={changed.length === 0 && save.state === "idle"}
            state={save.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            Save changes
          </Button>
          {changed.length === 0 ? null : (
            <>
              <span className="text-xs text-muted-foreground">
                {changed.length === 1 ? "1 change" : `${String(changed.length)} changes`}
              </span>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraft(initial);
                  setShown(false);
                  setServer({});
                }}
              >
                Undo changes
              </Button>
            </>
          )}
        </div>
      ) : null}
    </form>
  );
}

function SettingCard({
  setting,
  canEdit,
  value,
  error,
  onChange,
}: {
  setting: Setting;
  canEdit: boolean;
  value: string | readonly string[];
  error: string | undefined;
  onChange: (next: string | readonly string[]) => void;
}): React.JSX.Element {
  const id = `setting-${setting.key}`;
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>{settingTitle(setting.key)}</CardTitle>
          <CardDescription>{setting.description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <Field data-invalid={error === undefined ? undefined : true}>
          {canEdit ? (
            <SettingEditor
              id={id}
              setting={setting}
              value={value}
              error={error}
              onChange={onChange}
            />
          ) : (
            <p className="text-sm font-medium text-foreground">
              <ReadOnlyValue setting={setting} />
            </p>
          )}
          <FieldError id={`${id}-error`}>{error}</FieldError>
        </Field>
        {COPY[setting.key]?.note === undefined ? null : (
          <p className="text-xs text-muted-foreground">{COPY[setting.key]?.note}</p>
        )}
        <p className="text-xs text-muted-foreground">
          Changed <RelativeDate value={setting.updatedAt} />
        </p>
      </CardContent>
    </Card>
  );
}

function ReadOnlyValue({ setting }: { setting: Setting }): React.JSX.Element {
  const roles = useQuery({ ...roleListQueryOptions(), enabled: setting.kind === "roles" });
  switch (setting.kind) {
    case "choice":
      return <>{choiceLabel(setting.key, setting.value)}</>;
    case "int":
      return <>{formatNumber(setting.value)}</>;
    case "bands":
      return <>{setting.value.map((value) => formatNumber(value)).join(", ")}</>;
    case "slabs":
      return <>{slabsInOrder(setting.value).map(formatRate).join(", ")}</>;
    case "roles":
      return (
        <>
          {setting.value.length === 0
            ? "No one"
            : setting.value
                .map(
                  (code) => roles.data?.find((role) => role.code === code)?.name ?? humanize(code),
                )
                .join(COPY[setting.key]?.ordered === true ? ", then " : ", ")}
        </>
      );
  }
}

function SettingEditor({
  id,
  setting,
  value,
  error,
  onChange,
}: {
  id: string;
  setting: Setting;
  value: string | readonly string[];
  error: string | undefined;
  onChange: (next: string | readonly string[]) => void;
}): React.JSX.Element {
  const describedBy = error === undefined ? `${id}-hint` : `${id}-error`;
  const invalid = error === undefined ? undefined : true;
  const title = settingTitle(setting.key);

  if (setting.kind === "choice") {
    return (
      <RadioGroup<string>
        aria-label={title}
        value={typeof value === "string" ? value : setting.value}
        onValueChange={onChange}
        className="gap-2"
      >
        {setting.allowed.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-foreground">
            <RadioGroupItem value={option} />
            {choiceLabel(setting.key, option)}
          </label>
        ))}
      </RadioGroup>
    );
  }
  if (setting.kind === "int") {
    return (
      <>
        <FieldLabel htmlFor={id} className="sr-only">
          {title}
        </FieldLabel>
        <Input
          id={id}
          inputMode="numeric"
          className="w-32 tabular-nums"
          value={typeof value === "string" ? value : ""}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
        {error === undefined && (setting.min !== null || setting.max !== null) ? (
          <FieldDescription id={`${id}-hint`}>
            {setting.min !== null && setting.max !== null
              ? `${formatNumber(setting.min)} to ${formatNumber(setting.max)}.`
              : setting.min !== null
                ? `At least ${formatNumber(setting.min)}.`
                : `At most ${formatNumber(setting.max)}.`}
          </FieldDescription>
        ) : null}
      </>
    );
  }
  if (setting.kind === "roles") {
    return (
      <RolesEditor
        id={id}
        title={title}
        ordered={COPY[setting.key]?.ordered === true}
        value={Array.isArray(value) ? value : []}
        onChange={onChange}
      />
    );
  }
  if (setting.kind === "slabs") {
    const picked = Array.isArray(value) ? value : [];
    return (
      <div
        role="group"
        aria-label={title}
        aria-describedby={error === undefined ? undefined : describedBy}
        className="flex flex-wrap gap-x-5 gap-y-2"
      >
        {slabsInOrder([...GST_SLABS, ...setting.value]).map((slab) => (
          <label key={slab} className="flex min-h-9 items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={picked.includes(slab)}
              onCheckedChange={(checked) => {
                onChange(checked ? [...picked, slab] : picked.filter((item) => item !== slab));
              }}
            />
            {formatRate(slab)}
          </label>
        ))}
      </div>
    );
  }
  const bands = Array.isArray(value) ? value : [];
  return (
    <div role="group" aria-label={title} className="flex flex-wrap gap-2">
      {[0, 1, 2, 3].map((index) => (
        <Input
          key={index}
          aria-label={`${title}, band ${String(index + 1)}`}
          inputMode="numeric"
          className="w-24 tabular-nums"
          value={bands[index] ?? ""}
          aria-invalid={invalid}
          onChange={(event) => {
            const next = [0, 1, 2, 3].map((slot) =>
              slot === index ? event.target.value : (bands[slot] ?? ""),
            );
            onChange(next);
          }}
        />
      ))}
    </div>
  );
}

/**
 * Staff roles, by name: the codes saved are the backend's. An ordered one (an approval chain)
 * keeps the order they were ticked in, and says it.
 */
function RolesEditor({
  id,
  title,
  ordered,
  value,
  onChange,
}: {
  id: string;
  title: string;
  ordered: boolean;
  value: readonly string[];
  onChange: (next: readonly string[]) => void;
}): React.JSX.Element {
  const roles = useQuery(roleListQueryOptions());
  if (roles.isPending) {
    return <Skeleton className="h-16 w-full" />;
  }
  if (roles.isError) {
    return (
      <p className="text-sm text-muted-foreground">
        The roles couldn&apos;t be loaded: {value.join(", ") || "none chosen"}.
      </p>
    );
  }
  const staff = roles.data.filter((role) => !role.portal);
  const nameOf = (code: string): string =>
    staff.find((role) => role.code === code)?.name ?? humanize(code);
  return (
    <>
      <div
        role="group"
        aria-label={title}
        aria-describedby={ordered ? `${id}-order` : undefined}
        className="grid gap-2 sm:grid-cols-2"
      >
        {staff.map((role) => (
          <label
            key={role.code}
            className="flex min-h-9 items-center gap-2 text-sm text-foreground"
          >
            <Checkbox
              checked={value.includes(role.code)}
              onCheckedChange={(checked) => {
                onChange(
                  checked ? [...value, role.code] : value.filter((code) => code !== role.code),
                );
              }}
            />
            {role.name}
          </label>
        ))}
      </div>
      {ordered ? (
        <FieldDescription id={`${id}-order`}>
          {value.length === 0
            ? "No one yet. They approve in the order they're ticked."
            : `In this order: ${value.map(nameOf).join(", then ")}. To move one to the end, untick it and tick it again.`}
        </FieldDescription>
      ) : null}
    </>
  );
}

/** QUOT-015 · Slabs once each, lowest first: "0.25" and "0.250" are one slab. */
function slabsInOrder(slabs: readonly string[]): string[] {
  return [...new Set(slabs.map((slab) => String(Number(slab))))].sort(
    (a, b) => Number(a) - Number(b),
  );
}

function SettingsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading settings" className="flex flex-col gap-4">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-28 w-full" />
      ))}
    </div>
  );
}
