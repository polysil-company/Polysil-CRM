"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { useCreateScheme, usePatchScheme } from "@/features/schemes/api/schemes.mutations";
import {
  CONDITION_METRICS,
  DEFAULT_ENTITLEMENT_DAYS,
  KINDS_FOR_TYPE,
  SCHEME_PERIODS,
  SCHEME_TYPES,
  type BenefitKind,
  type ConditionMetric,
  type Scheme,
  type SchemeCreateRequest,
  type SchemePatchRequest,
  type SchemePeriod,
  type SchemeType,
} from "@/features/schemes/api/schemes.schemas";
import {
  PERIOD_LABELS,
  SCHEME_TYPE_DESCRIPTIONS,
  SCHEME_TYPE_LABELS,
} from "@/features/schemes/lib/scheme-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { TargetsEditor, type DraftTarget } from "./scheme-targets";

const log = createLogger({
  file: "features/schemes/components/scheme-form.tsx",
  dataId: "SCHM-002",
});

const KIND_LABELS: Readonly<Record<BenefitKind, string>> = {
  pct: "A percentage",
  flat: "A flat amount",
  points: "Points",
};

const METRIC_LABELS: Readonly<Record<ConditionMetric, string>> = {
  order_value: "Order value, before GST",
  product_qty: "Quantity",
};

interface Draft {
  code: string;
  name: string;
  description: string;
  type: SchemeType;
  metric: ConditionMetric;
  min: string;
  max: string;
  kind: BenefitKind;
  value: string;
  cap: string;
  days: string;
  period: SchemePeriod;
  validFrom: string;
  validTo: string;
  priority: string;
  stackable: boolean;
  targets: readonly DraftTarget[];
}

type FieldKey = Exclude<keyof Draft, "stackable">;

/** "200000.000" reads as "200000"; trailing zeros after the point go. */
function plain(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

function draftOf(scheme: Scheme | null): Draft {
  if (scheme === null) {
    return {
      code: "",
      name: "",
      description: "",
      type: "order_discount",
      metric: "order_value",
      min: "0",
      max: "",
      kind: "pct",
      value: "",
      cap: "",
      days: "",
      period: "month",
      validFrom: todayInIndia(),
      validTo: "",
      priority: "100",
      stackable: false,
      targets: [],
    };
  }
  return {
    code: scheme.code,
    name: scheme.name,
    description: scheme.description ?? "",
    type: scheme.type,
    metric: scheme.condition.metric,
    min: plain(scheme.condition.min),
    max: scheme.condition.max === null ? "" : plain(scheme.condition.max),
    kind: scheme.benefit.kind,
    value: plain(scheme.benefit.value),
    cap: scheme.benefit.cap === null ? "" : plain(scheme.benefit.cap),
    days: scheme.benefit.entitlementDays === null ? "" : String(scheme.benefit.entitlementDays),
    period: scheme.period ?? "month",
    validFrom: scheme.validFrom,
    validTo: scheme.validTo ?? "",
    priority: String(scheme.priority),
    stackable: scheme.stackable,
    targets: scheme.targets.map((target) => ({
      type: target.type,
      id: target.id,
      name: target.name ?? null,
    })),
  };
}

/** A benefit used on a later order expires: next-order credits, and a period's credit. */
function takesDays(draft: Pick<Draft, "type" | "kind">): boolean {
  return draft.type === "next_order" || (draft.type === "period" && draft.kind !== "points");
}

const NUMBER = /^\d+(\.\d+)?$/;

/** Why the draft won't do, by field, before the backend checks it again. */
function problemsOf(draft: Draft, creating: boolean): Partial<Record<FieldKey, string>> {
  const out: Partial<Record<FieldKey, string>> = {};
  if (creating && !/^[A-Za-z0-9_-]{2,40}$/.test(draft.code.trim())) {
    out.code = "2 to 40 letters, digits, - or _.";
  }
  if (draft.name.trim() === "") out.name = "Give the scheme a name.";
  if (!NUMBER.test(draft.min.trim())) out.min = "A number, 0 or more.";
  if (draft.max.trim() !== "") {
    if (!NUMBER.test(draft.max.trim())) out.max = "A number, or leave it empty.";
    else if (Number(draft.max) < Number(draft.min)) out.max = "At least the minimum.";
  }
  const value = draft.value.trim();
  if (!NUMBER.test(value) || Number(value) <= 0) out.value = "More than zero.";
  else if (draft.kind === "pct" && Number(value) > 100) out.value = "A percentage is at most 100.";
  else if (draft.kind === "points" && !/^\d+$/.test(value)) out.value = "Points are whole numbers.";
  if (draft.kind !== "points" && draft.cap.trim() !== "") {
    if (!NUMBER.test(draft.cap.trim()) || Number(draft.cap) <= 0) {
      out.cap = "More than zero, or leave it empty.";
    }
  }
  if (takesDays(draft) && draft.days.trim() !== "") {
    const days = Number(draft.days);
    if (!/^\d+$/.test(draft.days.trim()) || days < 1 || days > 3650) {
      out.days = "Between 1 and 3,650 days.";
    }
  }
  if (draft.validFrom === "") out.validFrom = "Pick the first day.";
  if (draft.type === "period" && draft.validTo === "") {
    out.validTo = "A period scheme needs an end date.";
  } else if (draft.validTo !== "" && draft.validTo < draft.validFrom) {
    out.validTo = "On or after the first day.";
  }
  const priority = Number(draft.priority);
  if (!/^\d+$/.test(draft.priority.trim()) || priority > 10000) out.priority = "0 to 10,000.";
  return out;
}

function requestOf(draft: Draft): SchemeCreateRequest {
  const points = draft.kind === "points";
  return {
    code: draft.code.trim(),
    name: draft.name.trim(),
    description: draft.description.trim() === "" ? null : draft.description.trim(),
    scheme_type: draft.type,
    condition: {
      metric: draft.metric,
      min: draft.min.trim(),
      max: draft.max.trim() === "" ? null : draft.max.trim(),
    },
    benefit: {
      kind: draft.kind,
      value: draft.value.trim(),
      cap: points || draft.cap.trim() === "" ? null : draft.cap.trim(),
      entitlement_days: takesDays(draft) && draft.days.trim() !== "" ? Number(draft.days) : null,
    },
    period: draft.type === "period" ? draft.period : null,
    valid_from: draft.validFrom,
    valid_to: draft.validTo === "" ? null : draft.validTo,
    priority: Number(draft.priority),
    stackable: draft.stackable,
    targets: draft.targets.map((target) => ({ type: target.type, id: target.id })),
  };
}

/** Only what changed, field by field; `targets` goes whole when it changed at all. */
function patchOf(before: SchemeCreateRequest, after: SchemeCreateRequest): SchemePatchRequest {
  const changed = (key: keyof SchemeCreateRequest): boolean =>
    JSON.stringify(before[key]) !== JSON.stringify(after[key]);
  return {
    ...(changed("name") ? { name: after.name } : {}),
    ...(changed("description") ? { description: after.description } : {}),
    ...(changed("scheme_type") ? { scheme_type: after.scheme_type } : {}),
    ...(changed("condition") ? { condition: after.condition } : {}),
    ...(changed("benefit") ? { benefit: after.benefit } : {}),
    ...(changed("period") ? { period: after.period } : {}),
    ...(changed("valid_from") ? { valid_from: after.valid_from } : {}),
    ...(changed("valid_to") ? { valid_to: after.valid_to } : {}),
    ...(changed("priority") ? { priority: after.priority } : {}),
    ...(changed("stackable") ? { stackable: after.stackable } : {}),
    ...(changed("targets") ? { targets: after.targets } : {}),
  };
}

/** The backend's field paths, onto this form's fields. */
const SERVER_FIELDS: Readonly<Record<string, FieldKey>> = {
  code: "code",
  name: "name",
  description: "description",
  scheme_type: "type",
  "condition.metric": "metric",
  "condition.min": "min",
  "condition.max": "max",
  "benefit.kind": "kind",
  "benefit.value": "value",
  "benefit.cap": "cap",
  "benefit.entitlement_days": "days",
  period: "period",
  valid_from: "validFrom",
  valid_to: "validTo",
  priority: "priority",
  targets: "targets",
};

function serverField(path: string): FieldKey | null {
  if (path.startsWith("targets")) return "targets";
  return SERVER_FIELDS[path] ?? null;
}

/**
 * SCHM-002 · Create a scheme, or change one. Once a scheme has given a benefit, only its end
 * date can change here (and it can be switched off on its page): the rest shows as it stands.
 */
export function SchemeForm({ scheme }: { scheme: Scheme | null }): React.JSX.Element {
  const router = useRouter();
  const creating = scheme === null;
  const locked = scheme?.used === true;
  const create = useCreateScheme();
  const patch = usePatchScheme();
  const idempotency = useIdempotencyKey();
  const initial = draftOf(scheme);
  const [draft, setDraft] = useState<Draft>(initial);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Partial<Record<FieldKey, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);

  const local = problemsOf(draft, creating);
  const relevant: Partial<Record<FieldKey, string>> = locked
    ? local.validTo === undefined
      ? {}
      : { validTo: local.validTo }
    : local;
  const errorOf = (key: FieldKey): string | undefined =>
    server[key] ?? (shown ? relevant[key] : undefined);

  const set = (next: Partial<Draft>): void => {
    setDraft((current) => {
      const merged = { ...current, ...next };
      // A type takes only some benefits: keep the kind one it takes.
      if (!KINDS_FOR_TYPE[merged.type].includes(merged.kind)) {
        merged.kind = KINDS_FOR_TYPE[merged.type][0] ?? "pct";
      }
      return merged;
    });
    setServer({});
  };

  const save = useAsyncAction({
    action: async () => {
      if (scheme === null) {
        const body = requestOf(draft);
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      const after = requestOf(draft);
      const body: SchemePatchRequest = locked
        ? { valid_to: after.valid_to }
        : patchOf(requestOf(initial), after);
      return patch.mutateAsync({
        schemeId: scheme.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: creating ? "handleCreateScheme" : "handleSaveScheme",
    dataId: "SCHM-002",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(creating ? "Scheme created" : "Scheme saved");
      router.push(`/schemes/${saved.id}`);
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "code_taken") {
        setServer({ code: "Another scheme has this code." });
        return;
      }
      if (isApiError(error) && error.code === "scheme_in_use") {
        setRefusal(
          "This scheme has given benefits since you opened it. Only its end date can change now; end it and create a new one.",
        );
        return;
      }
      const fields = readFieldErrors(error);
      if (fields !== null) {
        const mapped: Partial<Record<FieldKey, string>> = {};
        for (const [path, message] of Object.entries(fields)) {
          const key = serverField(path);
          if (key !== null) mapped[key] = `The backend refused it: ${message}`;
        }
        if (Object.keys(mapped).length > 0) {
          setServer(mapped);
          return;
        }
      }
      setRefusal(toUserFacingError(error).description);
    },
  });

  const unchanged = !creating && JSON.stringify(draft) === JSON.stringify(initial);
  const field = (
    key: FieldKey,
    label: string,
    input: (props: {
      id: string;
      "aria-invalid": true | undefined;
      "aria-describedby": string | undefined;
    }) => React.ReactNode,
    hint?: string,
  ): React.JSX.Element => {
    const id = `scheme-${key}`;
    const error = errorOf(key);
    return (
      <Field data-invalid={error === undefined ? undefined : true}>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        {input({
          id,
          "aria-invalid": error === undefined ? undefined : true,
          "aria-describedby":
            error === undefined ? (hint === undefined ? undefined : `${id}-hint`) : `${id}-error`,
        })}
        {error === undefined && hint !== undefined ? (
          <FieldDescription id={`${id}-hint`}>{hint}</FieldDescription>
        ) : null}
        <FieldError id={`${id}-error`}>{error}</FieldError>
      </Field>
    );
  };
  const text = (key: Exclude<FieldKey, "targets" | "type" | "metric" | "kind" | "period">) =>
    function TextInput(props: {
      id: string;
      "aria-invalid": true | undefined;
      "aria-describedby": string | undefined;
    }): React.JSX.Element {
      return (
        <Input
          {...props}
          value={draft[key]}
          disabled={locked ? key !== "validTo" : false}
          inputMode={
            ["min", "max", "value", "cap", "days", "priority"].includes(key) ? "decimal" : undefined
          }
          onChange={(event) => {
            set({ [key]: event.target.value });
          }}
        />
      );
    };

  return (
    <form
      noValidate
      aria-label={creating ? "New scheme" : `Edit ${scheme.name}`}
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        setServer({});
        if (Object.keys(relevant).length > 0) return;
        if (unchanged) {
          setRefusal("Nothing changed yet.");
          return;
        }
        void save.run();
      }}
    >
      {locked ? (
        <Notice tone="info">
          This scheme has given benefits, so only its end date can change here (an earlier one, not
          before today), and it can be switched off on its page. To change its terms, end it and
          create a new one.
        </Notice>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle level={2}>The scheme</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {field(
            "code",
            "Code",
            (props) => (
              <Input
                {...props}
                className="font-mono"
                value={draft.code}
                disabled={!creating}
                onChange={(event) => {
                  set({ code: event.target.value });
                }}
              />
            ),
            creating
              ? "Unique: letters, digits, - and _. It can't change later."
              : "A code can't change.",
          )}
          {field("name", "Name", text("name"))}
          <div className="sm:col-span-2">
            {field("description", "Description (optional)", (props) => (
              <Textarea
                {...props}
                rows={2}
                value={draft.description}
                disabled={locked}
                onChange={(event) => {
                  set({ description: event.target.value });
                }}
              />
            ))}
          </div>
          <fieldset className="flex flex-col gap-2 sm:col-span-2" disabled={locked}>
            <legend className="mb-2 text-sm font-medium text-foreground">Type</legend>
            <RadioGroup<SchemeType>
              aria-label="Type"
              value={draft.type}
              onValueChange={(type) => {
                set({ type });
              }}
              className="grid gap-2 sm:grid-cols-2"
            >
              {SCHEME_TYPES.map((type) => (
                <label
                  key={type}
                  className="flex items-start gap-2 rounded-lg border border-border p-3 text-sm text-foreground"
                >
                  <RadioGroupItem value={type} disabled={locked} className="mt-0.5" />
                  <span className="flex flex-col gap-0.5">
                    <span className="font-medium">{SCHEME_TYPE_LABELS[type]}</span>
                    <span className="text-xs text-muted-foreground">
                      {SCHEME_TYPE_DESCRIPTIONS[type]}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={2}>Who qualifies</CardTitle>
            <CardDescription>
              {draft.type === "period"
                ? "The target for the month's or quarter's delivered total."
                : "The orders that qualify, by the lines the scheme counts."}
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <fieldset className="flex flex-col gap-2" disabled={locked}>
            <legend className="mb-2 text-sm font-medium text-foreground">Measured by</legend>
            <RadioGroup<ConditionMetric>
              aria-label="Measured by"
              value={draft.metric}
              onValueChange={(metric) => {
                set({ metric });
              }}
              className="gap-2"
            >
              {CONDITION_METRICS.map((metric) => (
                <label key={metric} className="flex items-center gap-2 text-sm text-foreground">
                  <RadioGroupItem value={metric} disabled={locked} />
                  {METRIC_LABELS[metric]}
                </label>
              ))}
            </RadioGroup>
          </fieldset>
          {field(
            "min",
            draft.metric === "order_value" ? "At least (₹)" : "At least (units)",
            text("min"),
            "0 means any order.",
          )}
          {field(
            "max",
            draft.metric === "order_value" ? "At most (₹, optional)" : "At most (units, optional)",
            text("max"),
            "Empty for no upper limit.",
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={2}>The benefit</CardTitle>
            <CardDescription>
              It never changes the invoice; it reduces what is owed.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <fieldset className="flex flex-col gap-2" disabled={locked}>
            <legend className="mb-2 text-sm font-medium text-foreground">Kind</legend>
            <RadioGroup<BenefitKind>
              aria-label="Kind of benefit"
              value={draft.kind}
              onValueChange={(kind) => {
                set({ kind });
              }}
              className="gap-2"
            >
              {KINDS_FOR_TYPE[draft.type].map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm text-foreground">
                  <RadioGroupItem value={kind} disabled={locked} />
                  {KIND_LABELS[kind]}
                </label>
              ))}
            </RadioGroup>
            {errorOf("kind") === undefined ? null : (
              <p className="text-xs text-danger">{errorOf("kind")}</p>
            )}
          </fieldset>
          {field(
            "value",
            draft.kind === "pct"
              ? "Percentage"
              : draft.kind === "flat"
                ? "Amount (₹)"
                : "How many points",
            text("value"),
          )}
          {draft.kind === "points"
            ? null
            : field(
                "cap",
                "Benefit cap (₹, optional)",
                text("cap"),
                "The most one benefit is worth.",
              )}
          {takesDays(draft)
            ? field(
                "days",
                "Credit lasts (days, optional)",
                text("days"),
                `${String(DEFAULT_ENTITLEMENT_DAYS)} when left empty.`,
              )
            : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle level={2}>When</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          {draft.type === "period" ? (
            <fieldset className="flex flex-col gap-2" disabled={locked}>
              <legend className="mb-2 text-sm font-medium text-foreground">Runs by</legend>
              <RadioGroup<SchemePeriod>
                aria-label="Runs by"
                value={draft.period}
                onValueChange={(period) => {
                  set({ period });
                }}
                className="gap-2"
              >
                {SCHEME_PERIODS.map((period) => (
                  <label key={period} className="flex items-center gap-2 text-sm text-foreground">
                    <RadioGroupItem value={period} disabled={locked} />
                    {PERIOD_LABELS[period]}
                  </label>
                ))}
              </RadioGroup>
            </fieldset>
          ) : null}
          {field("validFrom", "First day", (props) => (
            <Input
              {...props}
              type="date"
              value={draft.validFrom}
              disabled={locked}
              onChange={(event) => {
                set({ validFrom: event.target.value });
              }}
            />
          ))}
          {field(
            "validTo",
            draft.type === "period" ? "Last day" : "Last day (optional)",
            (props) => (
              <Input
                {...props}
                type="date"
                value={draft.validTo}
                min={locked ? todayInIndia() : draft.validFrom || undefined}
                max={locked ? (scheme.validTo ?? undefined) : undefined}
                onChange={(event) => {
                  set({ validTo: event.target.value });
                }}
              />
            ),
            draft.type === "period" ? undefined : "Empty for no end date.",
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle level={2}>Beside other schemes</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {field("priority", "Priority", text("priority"), "Lower runs first. 100 by default.")}
          <label className="flex items-start gap-2 pt-6 text-sm text-foreground">
            <Checkbox
              checked={draft.stackable}
              disabled={locked}
              onCheckedChange={(checked) => {
                set({ stackable: checked });
              }}
            />
            <span className="flex flex-col gap-0.5">
              Can apply beside another order discount
              <span className="text-xs text-muted-foreground">Otherwise it applies alone.</span>
            </span>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={2}>Who it&apos;s for</CardTitle>
            <CardDescription>
              Any of the same kind; all of different kinds. Nothing here means everyone.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <TargetsEditor
            value={draft.targets}
            disabled={locked}
            onChange={(targets) => {
              set({ targets });
            }}
          />
          {errorOf("targets") === undefined ? null : (
            <p role="alert" className="text-sm text-danger">
              {errorOf("targets")}
            </p>
          )}
        </CardContent>
      </Card>

      {refusal === null ? null : (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {creating ? "Create scheme" : "Save changes"}
        </Button>
        <Link
          href={creating ? "/schemes" : `/schemes/${scheme.id}`}
          className={buttonVariants({ variant: "ghost" })}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
