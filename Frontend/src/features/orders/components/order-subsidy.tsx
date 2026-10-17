"use client";

import { Edit02Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { useSetOrderSubsidy } from "@/features/orders/api/orders.mutations";
import type { Order } from "@/features/orders/api/orders.schemas";
import { parseWarnings } from "@/features/quotations/lib/quotation-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { RefusalAlert, useOrderRefusal } from "./order-dialog-shared";

const log = createLogger({
  file: "features/orders/components/order-subsidy.tsx",
  dataId: "SO-008",
});

/** The order warnings the subsidy card words itself; the notices leave them out. */
const SUBSIDY_WARNINGS: Readonly<Record<string, string>> = {
  subsidy_above_material:
    "The subsidy is now more than the material: the lines changed. Edit the subsidy before submitting.",
  farmer_payable_not_material_less_subsidy:
    "The farmer payable isn't the material less the subsidy. That's allowed; check it's what was agreed.",
};

export function isSubsidyWarning(code: string): boolean {
  return SUBSIDY_WARNINGS[code] !== undefined;
}

/**
 * SO-008 · A subsidised order's subsidy (FS-054): the material, what the scheme pays and what
 * the farmer pays, and the leads it covers (the first is the order's lead). The order collects
 * the farmer's share, at most its total, less scheme benefits (FS-055 rule 4). Staff may change the amounts on a draft.
 */
export function OrderSubsidyCard({ order }: { order: Order }): React.JSX.Element | null {
  const canEdit = useCan("sales_orders", "edit");
  const staff = useIsStaff();
  const [editing, setEditing] = useState(false);
  const { subsidy } = order;
  if (subsidy === null) return null;
  const draft = order.status === "draft";
  const warnings = draft
    ? parseWarnings(order.warnings).flatMap((warning) => {
        const text = SUBSIDY_WARNINGS[warning.code];
        return text === undefined ? [] : [text];
      })
    : [];
  const [first, ...others] = subsidy.leads;

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Subsidy</CardTitle>
          <CardDescription>
            What the scheme pays and what the farmer pays. The order collects the farmer&apos;s
            share, at most its total, less any scheme benefits.
          </CardDescription>
        </div>
        {draft && canEdit && staff ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditing(true);
            }}
          >
            <Icon icon={Edit02Icon} />
            Edit the subsidy
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {warnings.map((text) => (
          <Notice key={text} tone="warning">
            <p>{text}</p>
          </Notice>
        ))}
        <dl className="grid gap-2 sm:grid-cols-3">
          <Amount
            label={subsidy.materialIsTotal ? "Material (the order total)" : "Material"}
            value={subsidy.materialAmount}
          />
          <Amount label="The scheme pays" value={subsidy.subsidyAmount} strong />
          <Amount
            label={
              subsidy.farmerPayableIsDerived
                ? "The farmer pays (material less subsidy)"
                : "The farmer pays"
            }
            value={subsidy.farmerPayable}
            strong
          />
        </dl>
        <div className="flex flex-col gap-1 text-sm">
          <p className="text-xs text-muted-foreground">
            {subsidy.leads.length === 1 ? "Lead" : `${String(subsidy.leads.length)} leads`}
          </p>
          <ul aria-label="Leads on this order" className="flex flex-wrap gap-x-3 gap-y-1">
            {first === undefined ? null : (
              <li>
                <LeadLink lead={first} />{" "}
                <span className="text-muted-foreground">(the order&apos;s lead)</span>
              </li>
            )}
            {others.map((lead) => (
              <li key={lead.id}>
                <LeadLink lead={lead} />
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent size="sm">
          {editing ? (
            <OrderSubsidyForm
              order={order}
              onClose={() => {
                setEditing(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Amount({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md border border-border px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={
          strong
            ? "text-lg font-semibold text-foreground tabular-nums"
            : "text-sm text-foreground tabular-nums"
        }
      >
        {formatInr(value, { paise: true })}
      </dd>
    </div>
  );
}

function LeadLink({ lead }: { lead: { id: string; code: string | null } }): React.JSX.Element {
  if (lead.code === null) {
    return <span className="text-muted-foreground">a lead you cannot see</span>;
  }
  return (
    <Link
      href={`/leads/${lead.id}`}
      className="font-mono text-primary-text underline-offset-4 hover:underline"
    >
      {lead.code}
    </Link>
  );
}

type AmountField = "material_amount" | "subsidy_amount" | "farmer_payable";

/** "12.50" with at most two decimals, never negative; null when it is one. */
function moneyProblem(value: string): string | null {
  return /^\d+(\.\d{1,2})?$/.test(value.trim()) ? null : "Enter rupees, like 49000 or 49000.50.";
}

/**
 * The amounts on a draft: material (empty for the order total), the subsidy, and the farmer
 * payable (empty for material less subsidy, shown as a hint). The leads stay as they are.
 */
function OrderSubsidyForm({
  order,
  onClose,
}: {
  order: Order;
  onClose: () => void;
}): React.JSX.Element {
  const subsidy = order.subsidy;
  const save = useSetOrderSubsidy();
  const idempotency = useIdempotencyKey();
  const refusal = useOrderRefusal(order.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const [material, setMaterial] = useState(
    subsidy === null || subsidy.materialIsTotal ? "" : subsidy.materialAmount,
  );
  const [amount, setAmount] = useState(subsidy?.subsidyAmount ?? "");
  const [payable, setPayable] = useState(
    subsidy === null || subsidy.farmerPayableIsDerived ? "" : subsidy.farmerPayable,
  );
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<Partial<Record<AmountField, string>>>({});

  const local: Partial<Record<AmountField, string>> = {};
  const materialProblem = material.trim() === "" ? null : moneyProblem(material);
  if (materialProblem !== null) local.material_amount = materialProblem;
  const amountProblem = amount.trim() === "" ? "Enter the subsidy." : moneyProblem(amount);
  if (amountProblem !== null) local.subsidy_amount = amountProblem;
  const payableProblem = payable.trim() === "" ? null : moneyProblem(payable);
  if (payableProblem !== null) local.farmer_payable = payableProblem;
  const shownProblem = (field: AmountField): string | undefined =>
    (shown ? local[field] : undefined) ?? serverProblems[field];
  const base = material.trim() === "" ? order.totals.total : material.trim();
  const derived =
    moneyProblem(base) === null && moneyProblem(amount) === null
      ? Number(base) - Number(amount)
      : null;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        lead_ids: (subsidy?.leads ?? []).map((lead) => lead.id),
        subsidy_amount: amount.trim(),
        ...(material.trim() === "" ? {} : { material_amount: material.trim() }),
        ...(payable.trim() === "" ? {} : { farmer_payable: payable.trim() }),
      };
      return save.mutateAsync({
        id: order.id,
        input: { body, idempotencyKey: idempotency.keyFor(body) },
      });
    },
    logger: log,
    fn: "handleSaveOrderSubsidy",
    dataId: "SO-008",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Subsidy saved");
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<AmountField, string>> = {};
      for (const field of ["material_amount", "subsidy_amount", "farmer_payable"] as const) {
        const message = fields[field] ?? fields[`subsidy.${field}`];
        if (message !== undefined) mapped[field] = message;
      }
      setServerProblems(mapped);
      refusal.handle(error);
    },
  });

  return (
    <form
      noValidate
      aria-label="Edit the subsidy"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServerProblems({});
        refusal.clear();
        if (Object.keys(local).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>The subsidy</DialogTitle>
        <DialogDescription>
          The leads stay as they are. Leave the material empty for the order total, and the farmer
          payable empty for material less subsidy.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <MoneyInput
          id="order-subsidy-material"
          label="Material amount"
          optional
          placeholder={`Order total, ${formatInr(order.totals.total, { paise: true })}`}
          value={material}
          error={shownProblem("material_amount")}
          onChange={setMaterial}
        />
        <MoneyInput
          id="order-subsidy-amount"
          label="Subsidy"
          value={amount}
          error={shownProblem("subsidy_amount")}
          onChange={setAmount}
        />
        <MoneyInput
          id="order-subsidy-payable"
          label="Farmer payable"
          optional
          placeholder="Material less subsidy"
          description={
            derived === null
              ? "Empty: the material less the subsidy."
              : `Empty: material less subsidy, ${formatInr(derived.toFixed(2), { paise: true })}.`
          }
          value={payable}
          error={shownProblem("farmer_payable")}
          onChange={setPayable}
        />
        <RefusalAlert refusal={refusal.refusal} />
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
          Save the subsidy
        </Button>
      </DialogFooter>
    </form>
  );
}

function MoneyInput({
  id,
  label,
  optional = false,
  placeholder,
  description,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  optional?: boolean;
  placeholder?: string;
  description?: string;
  value: string;
  error: string | undefined;
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy = error !== undefined ? `${id}-error` : description ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <InputGroup>
        <InputGroupAddon>₹</InputGroupAddon>
        <InputGroupInput
          id={id}
          inputMode="decimal"
          autoComplete="off"
          className="tabular-nums"
          placeholder={placeholder}
          value={value}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={describedBy}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      </InputGroup>
      {description !== undefined && error === undefined ? (
        <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
