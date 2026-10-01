"use client";

import { Cancel01Icon, CheckmarkCircle02Icon, Clock01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { RelativeDate } from "@/components/patterns/relative-date";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import type { Order, OrderApprovalStep } from "@/features/orders/api/orders.schemas";
import { stepRoleLabel } from "@/features/orders/lib/order-labels";
import { useCanApprove } from "@/features/session/hooks/use-session";
import { cn } from "@/lib/utils";

type StepState = "approved" | "returned" | "current" | "later" | "stopped";

const STATE_TEXT: Readonly<Record<StepState, string>> = {
  approved: "Approved",
  returned: "Returned",
  current: "Waiting now",
  later: "Next",
  stopped: "Not reached",
};

const MARKER_CLASSES: Readonly<Record<StepState, string>> = {
  approved: "bg-success-soft text-success",
  returned: "bg-danger-soft text-danger",
  current: "bg-warning-soft text-warning",
  later: "bg-muted text-muted-foreground",
  stopped: "bg-muted text-subtle-foreground",
};

/** Each step's place in the chain, read from the decisions and the request's status. */
function stepStates(order: Order): StepState[] {
  const steps = order.approval?.steps ?? [];
  const open = order.approval?.status === "pending";
  const current = open ? steps.findIndex((step) => step.decision === null) : -1;
  return steps.map((step, index) => {
    if (step.decision === "approve") return "approved";
    if (step.decision === "reject") return "returned";
    if (index === current) return "current";
    return open ? "later" : "stopped";
  });
}

/**
 * SO-004, APPR-001 · The order's approval chain: its managers by value, then Accounts, then
 * Dispatch. Each step says who decided and why; the step waiting now links to the approvals
 * inbox for those who decide.
 */
export function OrderApproval({ order }: { order: Order }): React.JSX.Element | null {
  const canApprove = useCanApprove();
  const approval = order.approval;
  if (approval === null || approval.steps.length === 0) {
    return null;
  }
  const states = stepStates(order);
  const waiting = order.status === "submitted";

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle level={3}>Approval</CardTitle>
        {waiting && canApprove ? (
          <Link href="/approvals" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Open approvals
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        <ol
          aria-label="Approval steps, in order"
          className="flex flex-col gap-3 md:grid md:auto-cols-fr md:grid-flow-col md:gap-4"
        >
          {approval.steps.map((step, index) => (
            <Step key={step.id} step={step} state={states[index] ?? "later"} />
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function Step({ step, state }: { step: OrderApprovalStep; state: StepState }): React.JSX.Element {
  const icon =
    state === "approved"
      ? CheckmarkCircle02Icon
      : state === "returned"
        ? Cancel01Icon
        : Clock01Icon;
  return (
    <li
      aria-current={state === "current" ? "step" : undefined}
      className={cn(
        "flex min-w-0 gap-3 rounded-lg border border-border p-3",
        state === "current" && "border-warning",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-full",
          MARKER_CLASSES[state],
        )}
      >
        <Icon icon={icon} size="sm" />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-medium text-foreground">
          {step.seq}. {stepRoleLabel(step.role)}
        </p>
        <p className="text-xs text-muted-foreground">
          {STATE_TEXT[state]}
          {step.by === null ? null : <> · {step.by.name}</>}
          {step.decidedRole === null ? null : (
            <>
              {" "}
              for {stepRoleLabel(step.role)}, as {stepRoleLabel(step.decidedRole)}
            </>
          )}
        </p>
        {step.decidedAt === null ? null : (
          <RelativeDate value={step.decidedAt} className="text-xs text-muted-foreground" />
        )}
        {step.remark === null ? null : (
          <p className="text-sm wrap-break-word whitespace-pre-line text-foreground">
            “{step.remark}”
          </p>
        )}
      </div>
    </li>
  );
}
