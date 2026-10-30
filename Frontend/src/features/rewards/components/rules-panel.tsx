"use client";

import { Add01Icon, Award01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Icon } from "@/components/ui/icon";
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
import { useSaveRule } from "@/features/rewards/api/rewards.mutations";
import { rulesQueryOptions } from "@/features/rewards/api/rewards.queries";
import {
  RULE_BASES,
  RULE_HOLDERS,
  type RewardRule,
  type RuleBasis,
  type RuleHolder,
} from "@/features/rewards/api/rewards.schemas";
import {
  RULE_BASIS_LABELS,
  RULE_HOLDER_LABELS,
  ruleInWords,
} from "@/features/rewards/lib/reward-labels";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/rewards/components/rules-panel.tsx",
  dataId: "RWD-003",
});

const HOLDER_ITEMS = RULE_HOLDERS.map((value) => ({ value, label: RULE_HOLDER_LABELS[value] }));
const BASIS_ITEMS = RULE_BASES.map((value) => ({ value, label: RULE_BASIS_LABELS[value] }));

function windowText(rule: RewardRule): string {
  const from = `From ${formatBusinessDay(rule.validFrom)}`;
  return rule.validTo === null ? from : `${from} to ${formatBusinessDay(rule.validTo)}`;
}

/**
 * RWD-003 · The earning rules. Points are earned by them, nothing is called: on a delivered
 * order (for the dealer and the staff owner) and on a won lead (for the owner). A rule that
 * has awarded points keeps its terms: only its end date and active flag change.
 */
export function RulesPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const query = useQuery(rulesQueryOptions());
  const [editing, setEditing] = useState<RewardRule | "new" | null>(null);

  return (
    <section aria-label="Earning rules" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          Points arrive by these rules: on a delivered order&apos;s value before GST, or on a lead
          won. A voided dispatch takes them back.
        </p>
        {canEdit ? (
          <Button
            variant="outline"
            className="shrink-0"
            onClick={() => {
              setEditing("new");
            }}
          >
            <Icon icon={Add01Icon} />
            Add a rule
          </Button>
        ) : null}
      </div>
      <QueryView
        query={query}
        pending={<Skeleton className="h-32 w-full rounded-xl" />}
        isEmpty={(rules) => rules.length === 0}
        empty={
          <EmptyState
            icon={Award01Icon}
            title="No earning rules"
            description="Without a rule, no points are earned."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(rules) => (
          <ul aria-label="Rules" className="flex flex-col gap-2">
            {rules.map((rule) => (
              <li
                key={rule.id}
                className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                    {rule.name}
                    <span className="font-mono text-xs font-normal text-muted-foreground">
                      {rule.code}
                    </span>
                    {rule.active ? (
                      rule.validFrom > todayInIndia() ? (
                        <Badge variant="info" size="sm" dot>
                          Scheduled
                        </Badge>
                      ) : (
                        <Badge variant="success" size="sm" dot>
                          Active
                        </Badge>
                      )
                    ) : (
                      <Badge variant="neutral" size="sm">
                        Switched off
                      </Badge>
                    )}
                    {rule.used ? (
                      <Badge variant="outline" size="sm">
                        Has awarded points
                      </Badge>
                    ) : null}
                  </span>
                  <span className="text-sm text-foreground">{ruleInWords(rule)}</span>
                  <span className="text-xs text-muted-foreground">
                    {windowText(rule)} ·{" "}
                    {rule.expiryDays === null
                      ? "points never expire"
                      : `points last ${String(rule.expiryDays)} days`}
                  </span>
                </span>
                {canEdit ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="self-start"
                    aria-label={`Change ${rule.name}`}
                    onClick={() => {
                      setEditing(rule);
                    }}
                  >
                    Change
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </QueryView>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="md">
          {editing === null ? null : (
            <RuleForm
              rule={editing === "new" ? null : editing}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

type RuleField =
  "code" | "name" | "holder" | "points" | "per_amount" | "valid_from" | "valid_to" | "expiry_days";

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function RuleForm({
  rule,
  onClose,
}: {
  rule: RewardRule | null;
  onClose: () => void;
}): React.JSX.Element {
  const save = useSaveRule();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const locked = rule?.used === true;
  const [code, setCode] = useState(rule?.code ?? "");
  const [name, setName] = useState(rule?.name ?? "");
  const [holder, setHolder] = useState<RuleHolder>(rule?.holder ?? "partner");
  const [basis, setBasis] = useState<RuleBasis>(rule?.basis ?? "order_value");
  const [points, setPoints] = useState(rule === null ? "" : String(rule.points));
  const [perAmount, setPerAmount] = useState(rule?.perAmount ?? "");
  const [from, setFrom] = useState(rule?.validFrom ?? todayInIndia());
  const [to, setTo] = useState(rule?.validTo ?? "");
  const [expiry, setExpiry] = useState(
    rule?.expiryDays === null || rule === null ? "" : String(rule.expiryDays),
  );
  const [active, setActive] = useState(rule?.active ?? true);
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Partial<Record<RuleField, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const onOrders = basis === "order_value";
  const problems: Record<RuleField, string | null> = {
    code: rule === null && code.trim() === "" ? "Give it a short code, like DEALER-ORDER." : null,
    name: name.trim() === "" ? "Name it." : null,
    holder: basis === "lead_won" && holder !== "staff" ? "A won lead earns for staff only." : null,
    points: /^\d+$/.test(points.trim()) && Number(points) > 0 ? null : "Whole points, at least 1.",
    per_amount:
      onOrders && !(/^\d+(\.\d{1,2})?$/.test(perAmount.trim()) && Number(perAmount) > 0)
        ? "Rupees, like 1000."
        : null,
    valid_from: DATE.test(from) ? null : "Choose the day it starts.",
    valid_to: to !== "" && to < from ? "On or after the start." : null,
    expiry_days:
      expiry.trim() === "" || (/^\d+$/.test(expiry.trim()) && Number(expiry) > 0)
        ? null
        : "Whole days, or empty for never.",
  };
  const problemOf = (field: RuleField): string | null =>
    serverFields[field] ?? (shown ? problems[field] : null);
  // A used rule changes only its end date and active flag.
  const checked: readonly RuleField[] = locked
    ? ["valid_to"]
    : Object.keys(problems).filter((key): key is RuleField => key in problems);

  const submit = useAsyncAction({
    action: () => {
      if (rule !== null) {
        const body = locked
          ? { valid_to: to === "" ? null : to, is_active: active }
          : {
              name: name.trim(),
              points: Number(points),
              per_amount: onOrders ? perAmount.trim() : null,
              valid_from: from,
              valid_to: to === "" ? null : to,
              expiry_days: expiry.trim() === "" ? null : Number(expiry),
              is_active: active,
            };
        return save.mutateAsync({
          ruleId: rule.id,
          body,
          idempotencyKey: idempotency.keyFor({ id: rule.id, ...body }),
        });
      }
      const body = {
        code: code.trim().toUpperCase(),
        name: name.trim(),
        holder,
        basis,
        points: Number(points),
        per_amount: onOrders ? perAmount.trim() : null,
        valid_from: from,
        valid_to: to === "" ? null : to,
        expiry_days: expiry.trim() === "" ? null : Number(expiry),
      };
      return save.mutateAsync({ ruleId: null, body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: rule === null ? "handleAddRule" : "handleChangeRule",
    dataId: "RWD-003",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(rule === null ? "Rule added" : "Rule changed", { description: saved.name });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && Object.keys(fields).length > 0) {
        setServerFields(fields);
        return;
      }
      if (isApiError(error) && error.code === "code_taken") {
        setServerFields({ code: "Another rule has this code." });
        return;
      }
      setRefusal(
        isApiError(error) && error.code === "rule_in_use"
          ? "It has awarded points meanwhile, so only its end date and active flag can change."
          : toUserFacingError(error).title,
      );
    },
  });

  const text = (
    id: string,
    label: React.ReactNode,
    field: RuleField,
    value: string,
    onChange: (next: string) => void,
    extra: {
      inputMode?: "numeric" | "decimal";
      type?: "date";
      hint?: string;
      disabled?: boolean;
    } = {},
  ): React.JSX.Element => {
    const problem = problemOf(field);
    return (
      <Field data-invalid={problem === null ? undefined : true}>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <Input
          id={id}
          type={extra.type}
          inputMode={extra.inputMode}
          autoComplete="off"
          disabled={extra.disabled}
          value={value}
          aria-invalid={problem === null ? undefined : true}
          aria-describedby={
            problem !== null ? `${id}-error` : extra.hint === undefined ? undefined : `${id}-hint`
          }
          onChange={(event) => {
            onChange(event.target.value);
            setServerFields(({ [field]: _cleared, ...rest }) => rest);
          }}
        />
        {problem === null ? (
          extra.hint === undefined ? null : (
            <FieldDescription id={`${id}-hint`}>{extra.hint}</FieldDescription>
          )
        ) : (
          <FieldError id={`${id}-error`}>{problem}</FieldError>
        )}
      </Field>
    );
  };

  return (
    <form
      noValidate
      aria-label={rule === null ? "Add a rule" : `Change ${rule.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (checked.some((field) => problems[field] !== null)) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{rule === null ? "Add an earning rule" : `Change ${rule.name}`}</DialogTitle>
        <DialogDescription>
          {locked
            ? "It has awarded points, so its terms stay as they are: end it, or switch it off, and add a new one."
            : "Points are earned by it from its start date; nothing earned earlier changes."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {rule === null
            ? text("rule-code", "Code", "code", code, setCode, { hint: "Short and unique." })
            : null}
          {text("rule-name", "Name", "name", name, setName, { disabled: locked })}
        </div>
        {rule === null ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="rule-basis">Earned</FieldLabel>
              <Select
                items={BASIS_ITEMS}
                value={basis}
                onValueChange={(next) => {
                  const chosen = RULE_BASES.find((value) => value === next);
                  if (chosen === undefined) return;
                  setBasis(chosen);
                  if (chosen === "lead_won") setHolder("staff");
                }}
              >
                <SelectTrigger id="rule-basis" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BASIS_ITEMS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field data-invalid={problemOf("holder") === null ? undefined : true}>
              <FieldLabel htmlFor="rule-holder">By</FieldLabel>
              <Select
                items={HOLDER_ITEMS}
                value={holder}
                onValueChange={(next) => {
                  const chosen = RULE_HOLDERS.find((value) => value === next);
                  if (chosen !== undefined) setHolder(chosen);
                }}
              >
                <SelectTrigger
                  id="rule-holder"
                  className="w-full"
                  aria-invalid={problemOf("holder") === null ? undefined : true}
                  aria-describedby={problemOf("holder") === null ? undefined : "rule-holder-error"}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOLDER_ITEMS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {problemOf("holder") === null ? null : (
                <FieldError id="rule-holder-error">{problemOf("holder")}</FieldError>
              )}
            </Field>
          </div>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-3">
          {text("rule-points", "Points", "points", points, setPoints, {
            inputMode: "numeric",
            disabled: locked,
          })}
          {onOrders
            ? text("rule-per", "For every ₹", "per_amount", perAmount, setPerAmount, {
                inputMode: "decimal",
                hint: "Whole blocks only.",
                disabled: locked,
              })
            : null}
          {text(
            "rule-expiry",
            <>
              Points last <span className="font-normal text-muted-foreground">(days)</span>
            </>,
            "expiry_days",
            expiry,
            setExpiry,
            { inputMode: "numeric", hint: "Empty: they never expire.", disabled: locked },
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {text("rule-from", "From", "valid_from", from, setFrom, {
            type: "date",
            disabled: locked,
          })}
          {text(
            "rule-to",
            <>
              To <span className="font-normal text-muted-foreground">(optional)</span>
            </>,
            "valid_to",
            to,
            setTo,
            { type: "date", hint: "Empty: no end." },
          )}
        </div>
        {rule === null ? null : (
          <div className="flex items-center gap-2">
            <Checkbox
              id="rule-active"
              checked={active}
              onCheckedChange={(next) => {
                setActive(next);
              }}
            />
            <Label htmlFor="rule-active">Earning points now</Label>
          </div>
        )}
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
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {rule === null ? "Add rule" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
