"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { humanizeCode } from "@/features/lookups/lib/lookup-labels";
import { usePatchScoring } from "@/features/masters/api/masters.mutations";
import { scoringQueryOptions } from "@/features/masters/api/masters.queries";
import type { ScoringItem } from "@/features/masters/api/masters.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/masters/components/scoring-panel.tsx",
  dataId: "MSTR-010",
});

interface SettingCopy {
  readonly label: string;
  readonly help: string;
}

/**
 * What each setting does, from the backend's formula (backend/api/domain/leads.py,
 * `score_lead`): four factors from 0 to 1, each times its weight, rounded; the total's band
 * is hot or warm from its threshold, else cold.
 */
const SETTINGS: Readonly<Record<string, SettingCopy>> = {
  w_source: { label: "Source quality", help: "Points for the lead source's quality (0 to 1)." },
  w_value: { label: "Estimated value", help: "Points for the estimate, up to the value cap." },
  w_speed: { label: "Response speed", help: "Points for how soon the farmer was first contacted." },
  w_engagement: { label: "Engagement", help: "Points for activity on the lead, up to its cap." },
  value_cap: { label: "Value cap (₹)", help: "An estimate at or above this scores full points." },
  speed_fast_hours: {
    label: "Fast contact (hours)",
    help: "First contact within this many hours scores full points.",
  },
  speed_slow_hours: {
    label: "Slow contact (hours)",
    help: "Within this many hours scores half; later scores none.",
  },
  engagement_cap: {
    label: "Engagement cap (activities)",
    help: "This many notes, calls and changes score full points.",
  },
  threshold_hot: { label: "Hot from", help: "A score at or above this is hot." },
  threshold_warm: { label: "Warm from", help: "At or above this, and below hot, is warm." },
  dormant_after_days: {
    label: "Dormant after (days)",
    help: "An open lead with no activity for this long goes dormant.",
  },
};

const GROUPS: readonly { readonly title: string; readonly keys: readonly string[] }[] = [
  { title: "Weights", keys: ["w_source", "w_value", "w_speed", "w_engagement"] },
  {
    title: "Caps and timings",
    keys: ["value_cap", "speed_fast_hours", "speed_slow_hours", "engagement_cap"],
  },
  { title: "Bands", keys: ["threshold_hot", "threshold_warm"] },
];

/** Caps and hour bands must stay above zero, or the score divides by zero (backend rule 7). */
const POSITIVE_KEYS: ReadonlySet<string> = new Set([
  "value_cap",
  "engagement_cap",
  "speed_fast_hours",
  "speed_slow_hours",
  "dormant_after_days",
]);

/** "25.00" → "25": how a setting reads in its field. */
export function settingText(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/** Why a typed value can't be saved, or null. Weights may be 0; caps and hours may not. */
export function settingProblem(key: string, text: string): string | null {
  const value = text.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return "A number, up to two decimals.";
  if (POSITIVE_KEYS.has(key) && Number(value) <= 0) return "Must be more than 0.";
  return null;
}

/** The settings that changed, as PATCH /lookups/scoring takes them. */
export function changedSettings(
  items: readonly ScoringItem[],
  draft: Readonly<Record<string, string>>,
): Record<string, string> {
  const changed: Record<string, string> = {};
  for (const item of items) {
    const typed = draft[item.key];
    if (typed !== undefined && Number(typed.trim()) !== Number(item.value)) {
      changed[item.key] = typed.trim();
    }
  }
  return changed;
}

/**
 * MSTR-010 · The settings behind every lead's score: readable by anyone who sees Masters,
 * changed by those who may edit masters. A change counts from the next time a lead is
 * scored (a create, a stage change, a note, an assignment or a reopen).
 */
export function ScoringPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const query = useQuery(scoringQueryOptions());

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Lead scoring</CardTitle>
          <CardDescription>
            A lead&apos;s score adds four parts: source quality, estimated value, response speed and
            engagement, each up to its weight. The bands set hot, warm and cold.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<ScoringSkeleton />}
          isEmpty={(items) => items.length === 0}
          empty={<p className="text-sm text-muted-foreground">No score settings yet.</p>}
        >
          {(items) => <ScoringForm key={formKey(items)} items={items} canEdit={canEdit} />}
        </QueryView>
      </CardContent>
    </Card>
  );
}

/** A new answer from the server starts the form again from what is stored. */
function formKey(items: readonly ScoringItem[]): string {
  return items.map((item) => `${item.key}=${item.value}`).join("&");
}

function ScoringForm({
  items,
  canEdit,
}: {
  items: readonly ScoringItem[];
  canEdit: boolean;
}): React.JSX.Element {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(items.map((item) => [item.key, settingText(item.value)])),
  );
  const [problems, setProblems] = useState<Record<string, string>>({});
  const patch = usePatchScoring();
  const changed = changedSettings(items, draft);
  const changedCount = Object.keys(changed).length;
  const known = new Set(GROUPS.flatMap((group) => group.keys));
  const others = items.filter((item) => !known.has(item.key)).map((item) => item.key);
  const groups = others.length === 0 ? GROUPS : [...GROUPS, { title: "Other", keys: others }];
  const present = new Set(items.map((item) => item.key));
  const weightTotal = ["w_source", "w_value", "w_speed", "w_engagement"].reduce(
    (sum, key) => sum + (Number(draft[key] ?? 0) || 0),
    0,
  );

  const save = useAsyncAction({
    action: () => patch.mutateAsync({ values: changed }),
    logger: log,
    fn: "handleSaveScoring",
    dataId: "MSTR-010",
    onSuccess: () => {
      toast.success("Score settings saved", {
        description: "They count from the next time a lead is scored.",
      });
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      if (Object.keys(fields).length > 0) {
        setProblems(fields);
        return;
      }
      toast.error("Score settings not saved", {
        description: toUserFacingError(error).description,
      });
    },
  });

  return (
    <form
      noValidate
      aria-label="Lead scoring"
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        const found: Record<string, string> = {};
        for (const key of Object.keys(changed)) {
          const problem = settingProblem(key, changed[key] ?? "");
          if (problem !== null) found[key] = problem;
        }
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      {groups.map((group) => (
        <fieldset key={group.title} className="flex flex-col gap-3">
          <legend className="mb-2 text-sm font-medium text-foreground">{group.title}</legend>
          {group.title === "Weights" ? (
            <p className="text-xs text-muted-foreground">
              The weights add up to {String(weightTotal)}: the most a lead can score.
            </p>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            {group.keys
              .filter((key) => present.has(key))
              .map((key) => {
                const copy = SETTINGS[key] ?? { label: humanizeCode(key), help: "" };
                const id = `scoring-${key}`;
                const problem = problems[key];
                return (
                  <Field key={key} data-invalid={problem === undefined ? undefined : true}>
                    <FieldLabel htmlFor={id}>{copy.label}</FieldLabel>
                    <Input
                      id={id}
                      inputMode="decimal"
                      value={draft[key] ?? ""}
                      readOnly={!canEdit}
                      aria-invalid={problem === undefined ? undefined : true}
                      aria-describedby={problem === undefined ? `${id}-hint` : `${id}-error`}
                      onChange={(event) => {
                        const value = event.target.value;
                        setDraft((before) => ({ ...before, [key]: value }));
                      }}
                    />
                    {problem === undefined ? (
                      <FieldDescription id={`${id}-hint`}>{copy.help}</FieldDescription>
                    ) : null}
                    <FieldError id={`${id}-error`}>{problem}</FieldError>
                  </Field>
                );
              })}
          </div>
        </fieldset>
      ))}
      {canEdit ? (
        <div className="flex items-center justify-end gap-3">
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {changedCount === 0
              ? "Nothing changed yet."
              : `${String(changedCount)} ${changedCount === 1 ? "setting" : "settings"} changed.`}
          </span>
          <Button
            type="submit"
            disabled={changedCount === 0}
            state={save.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            Save the settings
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Only administrators of masters change these.
        </p>
      )}
    </form>
  );
}

function ScoringSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading the score settings"
      className="grid gap-4 sm:grid-cols-2"
    >
      {[0, 1, 2, 3, 4, 5].map((row) => (
        <div key={row} className="flex flex-col gap-1.5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-control-md w-full" />
        </div>
      ))}
    </div>
  );
}
