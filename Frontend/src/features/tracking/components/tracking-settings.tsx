"use client";

import { ViewIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/features/session/hooks/use-session";
import { useSaveTrackingPolicy } from "@/features/tracking/api/policy.mutations";
import {
  trackingPolicyQueryOptions,
  viewLogQueryOptions,
} from "@/features/tracking/api/policy.queries";
import type { Policy, ViewLogRow } from "@/features/tracking/api/policy.schemas";
import {
  draftOf,
  POLICY_WIRE_FIELDS,
  policyProblems,
  requestOf,
  WEEKDAYS,
  workDaysText,
  type PolicyDraft,
  type PolicyField,
} from "@/features/tracking/lib/policy-form";
import { minutesText } from "@/features/tracking/lib/tracking-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatCalendarDay, formatDateTime, formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tracking/components/tracking-settings.tsx",
  dataId: "TRK-006",
});

const TABS = ["policy", "views"] as const;
const ALL_PEOPLE = "all";

/**
 * TRK-006, TRK-007 · Tracking settings: the policy in force, saved as a new version from a
 * date (never edited), and who looked at whose location. The tab is in the URL.
 */
export function TrackingSettings(): React.JSX.Element {
  const [tab, setTab] = useQueryState("tab", parseAsStringLiteral(TABS).withDefault("policy"));
  return (
    <Tabs
      value={tab}
      onValueChange={(next) => {
        const chosen = TABS.find((value) => value === next);
        if (chosen !== undefined) void setTab(chosen === "policy" ? null : chosen);
      }}
      className="flex flex-col gap-5"
    >
      <TabsList aria-label="Tracking settings">
        <TabsTrigger value="policy">Policy</TabsTrigger>
        <TabsTrigger value="views">Who looked</TabsTrigger>
      </TabsList>
      <TabsContent value="policy">
        <PolicyPanel />
      </TabsContent>
      <TabsContent value="views">
        <ViewLogPanel />
      </TabsContent>
    </Tabs>
  );
}

function PolicyPanel(): React.JSX.Element {
  const query = useQuery(trackingPolicyQueryOptions());
  const canEdit = useCan("masters", "edit");
  const [editing, setEditing] = useState(false);

  if (query.status === "pending") {
    return (
      <div aria-busy="true" aria-label="Loading the policy" className="flex flex-col gap-3">
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }
  if (query.status === "error") {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const policy = query.data;
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex-wrap">
          <div className="flex min-w-0 flex-col gap-0.5">
            <CardTitle level={2}>The policy in force</CardTitle>
            <CardDescription>Since {formatDateTime(policy.effectiveFrom)}</CardDescription>
          </div>
          {canEdit ? (
            <Button
              onClick={() => {
                setEditing(true);
              }}
            >
              Save a new version
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Item label="A location every">
              {minutesText(Math.max(1, Math.round(policy.intervalSeconds / 60)))}, or every{" "}
              {formatNumber(policy.distanceFilterM)} m moved
            </Item>
            <Item label="Working hours">
              {policy.workStart} to {policy.workEnd}, {workDaysText(policy.workDays).toLowerCase()}
            </Item>
            <Item label="Location history kept">{formatNumber(policy.retentionDays)} days</Item>
            <Item label="Photo at check-out">
              {policy.visitPhotoRequired ? "Required" : "Optional"}
            </Item>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-col gap-0.5">
          <CardTitle level={2}>Consent, version {policy.consentVersion}</CardTitle>
          <CardDescription>
            What staff agree to before their first duty or check-in.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm whitespace-pre-line text-foreground">{policy.consentText}</p>
        </CardContent>
      </Card>
      {canEdit ? null : (
        <p className="text-sm text-muted-foreground">Those who edit masters save new versions.</p>
      )}

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent size="lg">
          {editing ? (
            <PolicyForm
              policy={policy}
              onDone={() => {
                setEditing(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Item({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}

/** TRK-006 · A new version, from the one in force, taking over from a date. */
export function PolicyForm({
  policy,
  onDone,
}: {
  policy: Policy;
  onDone: () => void;
}): React.JSX.Element {
  const [draft, setDraft] = useState<PolicyDraft>(() => draftOf(policy));
  const [problems, setProblems] = useState<Partial<Record<PolicyField, string>>>({});
  const mutation = useSaveTrackingPolicy();
  const keys = useIdempotencyKey();
  const consentChanged = draft.consentVersion.trim() !== policy.consentVersion;

  const set = (next: Partial<PolicyDraft>): void => {
    setDraft((before) => ({ ...before, ...next }));
  };
  const invalid = (field: PolicyField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  const save = useAsyncAction({
    action: () => {
      const body = requestOf(draft);
      return mutation.mutateAsync({ body, idempotencyKey: keys.keyFor(body) });
    },
    logger: log,
    fn: "handleSavePolicy",
    dataId: "TRK-006",
    onSuccess: (saved) => {
      keys.reset();
      toast.success("New version saved", {
        description: `Takes over ${formatDateTime(saved.effectiveFrom)}`,
      });
      onDone();
    },
    onError: (error) => {
      keys.reset();
      if (isApiError(error) && error.code === "policy_exists") {
        setProblems({ effectiveFrom: "A version already starts then. Choose another time." });
        return;
      }
      const mapped: Partial<Record<PolicyField, string>> = {};
      for (const [wire, message] of Object.entries(readFieldErrors(error) ?? {})) {
        const field = POLICY_WIRE_FIELDS[wire.split(".")[0] ?? wire];
        if (field !== undefined) mapped[field] = message;
      }
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error("Not saved", { description: toUserFacingError(error).description });
    },
  });

  const number = (
    field: "intervalSeconds" | "distanceFilterM" | "retentionDays",
    label: string,
    hint: string,
  ): React.JSX.Element => (
    <Field data-invalid={invalid(field)}>
      <FieldLabel htmlFor={`policy-${field}`}>{label}</FieldLabel>
      <Input
        id={`policy-${field}`}
        inputMode="numeric"
        value={draft[field]}
        aria-invalid={invalid(field)}
        aria-describedby={`policy-${field}-hint`}
        onChange={(event) => {
          set({ [field]: event.target.value });
        }}
      />
      <FieldDescription id={`policy-${field}-hint`}>{hint}</FieldDescription>
      <FieldError>{problems[field]}</FieldError>
    </Field>
  );

  return (
    <form
      noValidate
      aria-label="Save a new version"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = policyProblems(draft);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Save a new version</DialogTitle>
        <DialogDescription>
          The policy in force stays as it is until this one takes over. A version is never edited.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={invalid("effectiveFrom")}>
          <FieldLabel htmlFor="policy-from">Takes over</FieldLabel>
          <Input
            id="policy-from"
            type="datetime-local"
            value={draft.effectiveFrom}
            aria-invalid={invalid("effectiveFrom")}
            onChange={(event) => {
              set({ effectiveFrom: event.target.value });
            }}
            className="sm:w-64"
          />
          <FieldDescription>India time.</FieldDescription>
          <FieldError>{problems.effectiveFrom}</FieldError>
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          {number("intervalSeconds", "Seconds between locations", "15 to 3,600")}
          {number("distanceFilterM", "Or every so many metres", "0 to 5,000")}
          {number("retentionDays", "Days to keep locations", "7 to 3,650")}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={invalid("workStart")}>
            <FieldLabel htmlFor="policy-start">The working day starts</FieldLabel>
            <Input
              id="policy-start"
              type="time"
              value={draft.workStart}
              aria-invalid={invalid("workStart")}
              onChange={(event) => {
                set({ workStart: event.target.value });
              }}
            />
            <FieldError>{problems.workStart}</FieldError>
          </Field>
          <Field data-invalid={invalid("workEnd")}>
            <FieldLabel htmlFor="policy-end">And ends</FieldLabel>
            <Input
              id="policy-end"
              type="time"
              value={draft.workEnd}
              aria-invalid={invalid("workEnd")}
              onChange={(event) => {
                set({ workEnd: event.target.value });
              }}
            />
            <FieldError>{problems.workEnd}</FieldError>
          </Field>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium text-foreground">Working days</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {WEEKDAYS.map((weekday) => (
              <div key={weekday.day} className="flex items-center gap-2">
                <Checkbox
                  id={`policy-day-${String(weekday.day)}`}
                  checked={draft.workDays.includes(weekday.day)}
                  onCheckedChange={(checked) => {
                    set({
                      workDays: checked
                        ? [...draft.workDays, weekday.day]
                        : draft.workDays.filter((day) => day !== weekday.day),
                    });
                  }}
                />
                <Label htmlFor={`policy-day-${String(weekday.day)}`}>{weekday.short}</Label>
              </div>
            ))}
          </div>
          {problems.workDays === undefined ? null : (
            <p role="alert" className="text-sm text-danger">
              {problems.workDays}
            </p>
          )}
        </fieldset>
        <div className="flex items-start gap-2">
          <Checkbox
            id="policy-photo"
            checked={draft.visitPhotoRequired}
            onCheckedChange={(checked) => {
              set({ visitPhotoRequired: checked });
            }}
          />
          <Label htmlFor="policy-photo" className="flex flex-col items-start gap-0.5">
            <span className="text-sm">A photo is required to check out of a visit</span>
          </Label>
        </div>
        <Field data-invalid={invalid("consentVersion")}>
          <FieldLabel htmlFor="policy-consent-version">Consent version</FieldLabel>
          <Input
            id="policy-consent-version"
            value={draft.consentVersion}
            maxLength={20}
            aria-invalid={invalid("consentVersion")}
            onChange={(event) => {
              set({ consentVersion: event.target.value });
            }}
            className="sm:w-40"
          />
          <FieldDescription>
            {consentChanged
              ? "A new version: everyone is asked to agree again at their next duty or check-in."
              : "Keep it to leave consent as it is. Change it when the text changes in substance."}
          </FieldDescription>
          <FieldError>{problems.consentVersion}</FieldError>
        </Field>
        <Field data-invalid={invalid("consentText")}>
          <FieldLabel htmlFor="policy-consent-text">Consent text</FieldLabel>
          <Textarea
            id="policy-consent-text"
            rows={5}
            value={draft.consentText}
            maxLength={10_000}
            aria-invalid={invalid("consentText")}
            onChange={(event) => {
              set({ consentText: event.target.value });
            }}
          />
          <FieldError>{problems.consentText}</FieldError>
        </Field>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save version
        </Button>
      </DialogFooter>
    </form>
  );
}

const WHAT_TEXT: Readonly<Record<ViewLogRow["what"], string>> = {
  route: "the route of",
  visits: "the visits of",
  team: "the team map",
};

/** TRK-007 · Who looked at whose location and when, newest first, for one person or all. */
function ViewLogPanel(): React.JSX.Element {
  const [subject, setSubject] = useState<string>(ALL_PEOPLE);
  const all = useInfiniteQuery(viewLogQueryOptions(null));
  const query = useInfiniteQuery(viewLogQueryOptions(subject === ALL_PEOPLE ? null : subject));
  const people = new Map<string, string>();
  for (const row of all.data?.pages.flatMap((page) => page.items) ?? []) {
    if (row.subject !== null) people.set(row.subject.id, row.subject.name);
  }
  const options = [
    { value: ALL_PEOPLE, label: "Everyone" },
    ...[...people.entries()]
      .sort(([, left], [, right]) => left.localeCompare(right))
      .map(([value, label]) => ({ value, label })),
  ];
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1 sm:w-64">
        <Label htmlFor="view-log-person">Whose location</Label>
        <Select
          items={options}
          value={subject}
          onValueChange={(next) => {
            if (typeof next === "string") setSubject(next);
          }}
        >
          <SelectTrigger id="view-log-person" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading the view log" className="flex flex-col gap-2">
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ViewIcon}
          title="Nothing to show"
          description="Nobody has looked yet. Only Admin and the MD see this log."
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <Card>
          <CardContent className="pt-4">
            <ol
              aria-label="Who looked, newest first"
              className="flex flex-col divide-y divide-border"
            >
              {rows.map((row, index) => (
                <li
                  key={`${row.viewedAt}-${String(index)}`}
                  className="flex flex-col gap-0.5 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="text-sm text-foreground">
                    <span className="font-medium">{row.viewer.name}</span> looked at{" "}
                    {WHAT_TEXT[row.what]}
                    {row.subject === null ? null : (
                      <span className="font-medium"> {row.subject.name}</span>
                    )}
                    {row.viewedDate === null ? "" : ` for ${formatCalendarDay(row.viewedDate)}`}
                  </span>
                  <RelativeDate value={row.viewedAt} className="text-xs text-muted-foreground" />
                </li>
              ))}
            </ol>
            {query.hasNextPage ? (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  state={query.isFetchingNextPage ? "loading" : "idle"}
                  loadingLabel="Loading…"
                  onClick={() => {
                    void query.fetchNextPage();
                  }}
                >
                  Show more
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
