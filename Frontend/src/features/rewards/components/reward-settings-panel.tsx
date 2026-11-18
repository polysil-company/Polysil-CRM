"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Skeleton } from "@/components/ui/skeleton";
import { useSaveRewardSettings } from "@/features/rewards/api/rewards.mutations";
import { rewardSettingsQueryOptions } from "@/features/rewards/api/rewards.queries";
import type { RewardSettings } from "@/features/rewards/api/rewards.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/rewards/components/reward-settings-panel.tsx",
  dataId: "RWD-003",
});

/**
 * RWD-003 · What a point is worth on an order, and the most of an order points may pay. A
 * change applies from today, once a day; orders already submitted keep their own day's value.
 */
export function RewardSettingsPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const query = useQuery(rewardSettingsQueryOptions());
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Point value and limit</CardTitle>
        <CardDescription>
          A change applies from today, once a day. Orders already submitted keep their day&apos;s
          value.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <Skeleton className="h-28 w-full" />
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
            className="border-0 p-2"
          />
        ) : canEdit ? (
          <SettingsForm key={query.data.effectiveFrom} settings={query.data} />
        ) : (
          <SettingsFacts settings={query.data} />
        )}
      </CardContent>
    </Card>
  );
}

function SettingsFacts({ settings }: { settings: RewardSettings }): React.JSX.Element {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div className="flex flex-col gap-0.5">
        <dt className="text-xs text-muted-foreground">One point is worth</dt>
        <dd className="text-foreground">{formatInr(settings.pointValue, { paise: true })}</dd>
      </div>
      <div className="flex flex-col gap-0.5">
        <dt className="text-xs text-muted-foreground">Points may pay at most</dt>
        <dd className="text-foreground">{String(Number(settings.maxRedeemPct))}% of an order</dd>
      </div>
      <div className="flex flex-col gap-0.5 sm:col-span-2">
        <dt className="text-xs text-muted-foreground">Since</dt>
        <dd className="text-foreground">{formatBusinessDay(settings.effectiveFrom)}</dd>
      </div>
    </dl>
  );
}

function SettingsForm({ settings }: { settings: RewardSettings }): React.JSX.Element {
  const save = useSaveRewardSettings();
  const idempotency = useIdempotencyKey();
  const [value, setValue] = useState(settings.pointValue);
  const [pct, setPct] = useState(String(Number(settings.maxRedeemPct)));
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Readonly<Record<string, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const changedToday = settings.effectiveFrom === todayInIndia();
  const problems = {
    point_value:
      serverFields.point_value ??
      (/^\d+(\.\d{1,2})?$/.test(value.trim()) && Number(value) > 0
        ? null
        : "Rupees above 0, like 1 or 0.50."),
    max_redeem_pct:
      serverFields.max_redeem_pct ??
      (/^\d+(\.\d{1,2})?$/.test(pct.trim()) && Number(pct) <= 100 ? null : "From 0 to 100."),
  };
  const unchanged =
    Number(value) === Number(settings.pointValue) && Number(pct) === Number(settings.maxRedeemPct);

  const submit = useAsyncAction({
    action: () => {
      const body = { point_value: value.trim(), max_redeem_pct: pct.trim() };
      return save.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSaveRewardSettings",
    dataId: "RWD-003",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Point settings changed", {
        description: `${formatInr(saved.pointValue, { paise: true })} a point, at most ${String(Number(saved.maxRedeemPct))}% of an order, from today.`,
      });
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && Object.keys(fields).length > 0) {
        setServerFields(fields);
        return;
      }
      setRefusal(
        isApiError(error) && error.code === "settings_changed_today"
          ? "They were already changed today. Change them again tomorrow."
          : toUserFacingError(error).title,
      );
    },
  });
  const show = (key: keyof typeof problems): string | null =>
    shown || serverFields[key] !== undefined ? problems[key] : null;

  return (
    <form
      noValidate
      aria-label="Point settings"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problems.point_value !== null || problems.max_redeem_pct !== null) return;
        void submit.run();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field data-invalid={show("point_value") === null ? undefined : true}>
          <FieldLabel htmlFor="settings-value">One point is worth</FieldLabel>
          <InputGroup>
            <InputGroupAddon>₹</InputGroupAddon>
            <InputGroupInput
              id="settings-value"
              inputMode="decimal"
              autoComplete="off"
              className="tabular-nums"
              value={value}
              aria-invalid={show("point_value") === null ? undefined : true}
              aria-describedby={show("point_value") === null ? undefined : "settings-value-error"}
              onChange={(event) => {
                setValue(event.target.value);
                setServerFields(({ point_value: _cleared, ...rest }) => rest);
              }}
            />
          </InputGroup>
          {show("point_value") === null ? null : (
            <FieldError id="settings-value-error">{show("point_value")}</FieldError>
          )}
        </Field>
        <Field data-invalid={show("max_redeem_pct") === null ? undefined : true}>
          <FieldLabel htmlFor="settings-pct">Points may pay at most</FieldLabel>
          <InputGroup>
            <InputGroupInput
              id="settings-pct"
              inputMode="decimal"
              autoComplete="off"
              className="tabular-nums"
              value={pct}
              aria-invalid={show("max_redeem_pct") === null ? undefined : true}
              aria-describedby={
                show("max_redeem_pct") === null ? "settings-pct-hint" : "settings-pct-error"
              }
              onChange={(event) => {
                setPct(event.target.value);
                setServerFields(({ max_redeem_pct: _cleared, ...rest }) => rest);
              }}
            />
            <InputGroupAddon align="end">%</InputGroupAddon>
          </InputGroup>
          {show("max_redeem_pct") === null ? (
            <FieldDescription id="settings-pct-hint">
              Of an order&apos;s total, GST included.
            </FieldDescription>
          ) : (
            <FieldError id="settings-pct-error">{show("max_redeem_pct")}</FieldError>
          )}
        </Field>
      </div>
      <p className="text-xs text-muted-foreground">
        In force since {formatBusinessDay(settings.effectiveFrom)}.
        {changedToday ? " Changed today, so the next change is tomorrow." : ""}
      </p>
      {refusal === null ? null : (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}
      <Button
        type="submit"
        className="self-start"
        disabled={unchanged || changedToday}
        state={submit.state}
        loadingLabel="Saving…"
        successLabel="Saved"
        errorLabel="Not saved"
      >
        Save from today
      </Button>
    </form>
  );
}
