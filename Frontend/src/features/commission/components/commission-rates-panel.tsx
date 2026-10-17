"use client";

import { Add01Icon, Cancel01Icon, Coins01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAddCommissionRate } from "@/features/commission/api/commission.mutations";
import { commissionRatesQueryOptions } from "@/features/commission/api/commission.queries";
import {
  RATE_PARTNER_TYPES,
  RATE_SYSTEM_TYPES,
  type CommissionRate,
} from "@/features/commission/api/commission.schemas";
import {
  RATE_PARTNER_TYPE_LABELS,
  RATE_SYSTEM_LABELS,
  formatPct,
  labelFrom,
} from "@/features/commission/lib/commission-labels";
import { PartnerSearchPicker } from "@/features/schemes/components/record-pickers";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/commission/components/commission-rates-panel.tsx",
  dataId: "SUBS-018",
});

/** "Any" in a Select, since a Select item needs a string value. */
const ANY = "any";

/** The rate's scope in words, most specific first: who and which system. */
function scopeOf(rate: CommissionRate): string {
  const who =
    rate.partner !== null
      ? (rate.partner.name ?? "One partner")
      : labelFrom(RATE_PARTNER_TYPE_LABELS, rate.partnerType, "Every partner");
  const system = labelFrom(RATE_SYSTEM_LABELS, rate.systemType, "every system");
  return `${who} · ${rate.systemType === null ? system : system.toLowerCase()}`;
}

/** Of each scope, the latest rate already started is the one in force today. */
function inForceIds(rates: readonly CommissionRate[], today: string): ReadonlySet<string> {
  const seen = new Set<string>();
  const current = new Set<string>();
  for (const rate of [...rates].sort((left, right) =>
    right.effectiveFrom.localeCompare(left.effectiveFrom),
  )) {
    if (rate.effectiveFrom > today) continue;
    const scope = [rate.systemType, rate.partnerType, rate.partner?.id].join("|");
    if (seen.has(scope)) continue;
    seen.add(scope);
    current.add(rate.id);
  }
  return current;
}

/**
 * SUBS-018 · A scheme's dealer commission and TOD rates. The one used on an application is the
 * most specific in force on its full-FP date: one partner, then partner type, then system, then
 * the scheme. Rates are never edited; a later one supersedes, a 0% one retires the scope.
 */
export function CommissionRatesPanel({
  scheme,
  canEdit,
}: {
  scheme: string;
  canEdit: boolean;
}): React.JSX.Element {
  const query = useQuery(commissionRatesQueryOptions(scheme));
  const [adding, setAdding] = useState(false);
  const today = todayInIndia();

  return (
    <section aria-label="Commission rates" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          The dealer&apos;s commission and TOD at stage 18. An application takes the most specific
          rate in force on its full-FP date: one partner, then a partner type, then a system, then
          the whole scheme. Rates are never edited: add a later one, or a 0% one to retire it.
        </p>
        {canEdit ? (
          <Button
            variant="outline"
            className="shrink-0"
            onClick={() => {
              setAdding(true);
            }}
          >
            <Icon icon={Add01Icon} />
            Add a rate
          </Button>
        ) : null}
      </div>

      <QueryView
        query={query}
        pending={<RatesSkeleton />}
        isEmpty={(rates) => rates.length === 0}
        empty={
          <EmptyState
            icon={Coins01Icon}
            title={`No commission rates for ${scheme}`}
            description={
              canEdit
                ? "Add one so co-ordinators can record a dealer's commission at stage 18."
                : "An administrator adds them; until then, stage 18 can't be recorded."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(rates) => {
          const current = inForceIds(rates, today);
          return (
            <ul aria-label={`Commission rates for ${scheme}`} className="flex flex-col gap-2">
              {rates.map((rate) => (
                <li
                  key={rate.id}
                  className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4"
                >
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                      {scopeOf(rate)}
                      {current.has(rate.id) ? (
                        <Badge variant="success" size="sm" dot>
                          In force
                        </Badge>
                      ) : rate.effectiveFrom > today ? (
                        <Badge variant="info" size="sm" dot>
                          Scheduled
                        </Badge>
                      ) : (
                        <Badge variant="neutral" size="sm">
                          Superseded
                        </Badge>
                      )}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      From {formatBusinessDay(rate.effectiveFrom)}
                    </span>
                  </span>
                  <span className="text-sm text-foreground tabular-nums">
                    {Number(rate.commissionPct) === 0
                      ? "Retired: no commission"
                      : `${formatPct(rate.commissionPct)} commission · ${formatPct(rate.todPct)} TOD`}
                  </span>
                </li>
              ))}
            </ul>
          );
        }}
      </QueryView>

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent size="md">
          {adding ? (
            <AddRateForm
              scheme={scheme}
              onClose={() => {
                setAdding(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function RatesSkeleton(): React.JSX.Element {
  return (
    <div aria-busy="true" aria-label="Loading rates" className="flex flex-col gap-2">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  );
}

const SYSTEM_ITEMS = [
  { value: ANY, label: "Every system" },
  ...RATE_SYSTEM_TYPES.map((value) => ({ value, label: RATE_SYSTEM_LABELS[value] })),
];
const PARTNER_TYPE_ITEMS = [
  { value: ANY, label: "Every partner type" },
  ...RATE_PARTNER_TYPES.map((value) => ({ value, label: RATE_PARTNER_TYPE_LABELS[value] })),
];

type RateField = "commission_pct" | "tod_pct" | "effective_from" | "partner_id";

function pctProblem(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return "Enter a percentage, or 0.";
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return "A percentage, like 5 or 2.5.";
  return Number(trimmed) > 100 ? "At most 100." : null;
}

function AddRateForm({
  scheme,
  onClose,
}: {
  scheme: string;
  onClose: () => void;
}): React.JSX.Element {
  const add = useAddCommissionRate();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const today = todayInIndia();
  const [system, setSystem] = useState<string>(ANY);
  const [partnerType, setPartnerType] = useState<string>(ANY);
  const [partner, setPartner] = useState<{ id: string; name: string } | null>(null);
  const [commission, setCommission] = useState("");
  const [tod, setTod] = useState("");
  const [from, setFrom] = useState(today);
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Partial<Record<RateField, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems: Record<RateField, string | null> = {
    commission_pct: pctProblem(commission),
    tod_pct: pctProblem(tod),
    effective_from: /^\d{4}-\d{2}-\d{2}$/.test(from) ? null : "Choose the day it starts.",
    partner_id: null,
  };
  const problemOf = (field: RateField): string | null =>
    serverFields[field] ?? (shown ? problems[field] : null);

  const submit = useAsyncAction({
    action: () => {
      const body = {
        scheme,
        system_type: RATE_SYSTEM_TYPES.find((value) => value === system) ?? null,
        partner_type:
          partner === null
            ? (RATE_PARTNER_TYPES.find((value) => value === partnerType) ?? null)
            : null,
        partner_id: partner?.id ?? null,
        commission_pct: commission.trim(),
        tod_pct: tod.trim(),
        effective_from: from,
      };
      return add.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleAddCommissionRate",
    dataId: "SUBS-018",
    onSuccess: (rate) => {
      idempotency.reset();
      toast.success("Rate added", {
        description: `${scopeOf(rate)}, from ${formatBusinessDay(rate.effectiveFrom)}.`,
      });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && Object.keys(fields).length > 0) {
        setServerFields(fields);
        return;
      }
      setRefusal(
        isApiError(error) && error.code === "rate_exists"
          ? "A rate for the same scope already starts that day. Choose another day."
          : toUserFacingError(error).title,
      );
    },
  });

  const pctInput = (
    id: string,
    label: string,
    field: RateField,
    value: string,
    onChange: (next: string) => void,
  ): React.JSX.Element => (
    <Field data-invalid={problemOf(field) === null ? undefined : true}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <InputGroup>
        <InputGroupInput
          id={id}
          inputMode="decimal"
          autoComplete="off"
          className="tabular-nums"
          value={value}
          aria-invalid={problemOf(field) === null ? undefined : true}
          aria-describedby={problemOf(field) === null ? undefined : `${id}-error`}
          onChange={(event) => {
            onChange(event.target.value);
            setServerFields(({ [field]: _cleared, ...rest }) => rest);
          }}
        />
        <InputGroupAddon align="end">%</InputGroupAddon>
      </InputGroup>
      {problemOf(field) === null ? null : (
        <FieldError id={`${id}-error`}>{problemOf(field)}</FieldError>
      )}
    </Field>
  );

  return (
    <form
      noValidate
      aria-label="Add a commission rate"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.values(problems).some((problem) => problem !== null)) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Add a commission rate</DialogTitle>
        <DialogDescription>
          For the {scheme} scheme. Leave a choice at &quot;every&quot; for a wider rate; the most
          specific one in force wins.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="rate-system">System</FieldLabel>
            <Select
              items={SYSTEM_ITEMS}
              value={system}
              onValueChange={(next) => {
                setSystem(typeof next === "string" ? next : ANY);
              }}
            >
              <SelectTrigger id="rate-system" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SYSTEM_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="rate-partner-type">Partner type</FieldLabel>
            <Select
              items={PARTNER_TYPE_ITEMS}
              value={partner === null ? partnerType : ANY}
              disabled={partner !== null}
              onValueChange={(next) => {
                setPartnerType(typeof next === "string" ? next : ANY);
              }}
            >
              <SelectTrigger
                id="rate-partner-type"
                className="w-full"
                aria-describedby={partner === null ? undefined : "rate-partner-type-hint"}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PARTNER_TYPE_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {partner === null ? null : (
              <FieldDescription id="rate-partner-type-hint">
                One partner is chosen, so the type doesn&apos;t apply.
              </FieldDescription>
            )}
          </Field>
        </div>
        <Field data-invalid={problemOf("partner_id") === null ? undefined : true}>
          <FieldLabel htmlFor="rate-partner">
            One partner <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          {partner === null ? (
            <PartnerSearchPicker
              id="rate-partner"
              aria-describedby="rate-partner-hint"
              onPick={(picked) => {
                setPartner({ id: picked.id, name: picked.name });
                setServerFields(({ partner_id: _cleared, ...rest }) => rest);
              }}
            />
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <span className="text-foreground">{partner.name}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${partner.name}`}
                onClick={() => {
                  setPartner(null);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </div>
          )}
          {problemOf("partner_id") === null ? (
            <FieldDescription id="rate-partner-hint">
              Only for a rate agreed with one partner.
            </FieldDescription>
          ) : (
            <FieldError>{problemOf("partner_id")}</FieldError>
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          {pctInput("rate-commission", "Commission", "commission_pct", commission, setCommission)}
          {pctInput("rate-tod", "TOD", "tod_pct", tod, setTod)}
          <Field data-invalid={problemOf("effective_from") === null ? undefined : true}>
            <FieldLabel htmlFor="rate-from">From</FieldLabel>
            <Input
              id="rate-from"
              type="date"
              value={from}
              aria-invalid={problemOf("effective_from") === null ? undefined : true}
              aria-describedby={
                problemOf("effective_from") === null ? undefined : "rate-from-error"
              }
              onChange={(event) => {
                setFrom(event.target.value);
                setServerFields(({ effective_from: _cleared, ...rest }) => rest);
              }}
            />
            {problemOf("effective_from") === null ? null : (
              <FieldError id="rate-from-error">{problemOf("effective_from")}</FieldError>
            )}
          </Field>
        </div>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Adding…"
          successLabel="Added"
          errorLabel="Not added"
        >
          Add rate
        </Button>
      </DialogFooter>
    </form>
  );
}
