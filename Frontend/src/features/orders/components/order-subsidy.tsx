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
import { Icon } from "@/components/ui/icon";
import { useSetOrderSubsidy } from "@/features/orders/api/orders.mutations";
import type { Order } from "@/features/orders/api/orders.schemas";
import { parseWarnings } from "@/features/quotations/lib/quotation-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { RefusalAlert, useCloseAfterSuccess, useOrderRefusal } from "./order-dialog-shared";
import {
  SubsidyFields,
  subsidyDraftProblems,
  subsidyFieldErrors,
  subsidyRequest,
  type SubsidyDraft,
  type SubsidyProblems,
} from "./order-subsidy-fields";

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
        {order.payable === null ? null : (
          <p className="text-sm text-muted-foreground">
            Payable{" "}
            <span className="font-medium text-foreground tabular-nums">
              {formatInr(order.payable, { paise: true })}
            </span>
            : the farmer&apos;s share.
          </p>
        )}
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

/**
 * A draft's subsidy: the leads (the first stays first) and the amounts, as on the new-order
 * screen. Empty material is the order total; empty farmer payable is material less subsidy.
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
  const [draft, setDraft] = useState<SubsidyDraft>(() => ({
    leads: (subsidy?.leads ?? []).map((lead) => ({ id: lead.id, code: lead.code, name: null })),
    material: subsidy === null || subsidy.materialIsTotal ? "" : subsidy.materialAmount,
    amount: subsidy?.subsidyAmount ?? "",
    payable: subsidy === null || subsidy.farmerPayableIsDerived ? "" : subsidy.farmerPayable,
  }));
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<SubsidyProblems>({});
  const local = subsidyDraftProblems(draft);
  const problems: SubsidyProblems = { ...(shown ? local : {}), ...serverProblems };

  const submit = useAsyncAction({
    action: () => {
      const body = subsidyRequest(draft);
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
      setServerProblems(subsidyFieldErrors(error));
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
          Leave the material empty for the order total, and the farmer payable empty for material
          less subsidy.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <SubsidyFields
          idPrefix="order-subsidy"
          draft={draft}
          onDraftChange={(next) => {
            setDraft(next);
            setServerProblems({});
          }}
          problems={problems}
          total={order.totals.total}
          firstLeadFixed
          stacked
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
