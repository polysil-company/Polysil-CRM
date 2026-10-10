"use client";

import { Edit02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { approvalThresholdsQueryOptions } from "@/features/approvals/api/approvals.queries";
import type { Threshold, ThresholdDocType } from "@/features/approvals/api/approvals.schemas";
import { limitRoleLabel } from "@/features/approvals/lib/approval-labels";
import {
  formatLimit,
  ladderFor,
  overrideTerritories,
  type LadderStep,
} from "@/features/approvals/lib/approval-limits";
import { useCan } from "@/features/session/hooks/use-session";

import { ApprovalLimitDialog, type LimitTarget } from "./approval-limit-dialog";

const LADDERS: readonly {
  readonly docType: ThresholdDocType;
  readonly title: string;
  readonly explain: string;
  readonly unit: Threshold["unit"];
}[] = [
  {
    docType: "sales_order",
    title: "Order value",
    explain:
      "Including GST. Each manager approves orders up to their limit; a bigger order goes on to the next level, then to Accounts and Dispatch.",
    unit: "inr",
  },
  {
    docType: "quotation",
    title: "Discount on a quotation",
    explain:
      "A field officer sends a quotation with a discount up to their own limit. Above it, the lowest manager whose limit covers the discount approves it first.",
    unit: "pct",
  },
  {
    docType: "complaint",
    title: "Refund on a complaint",
    explain:
      "When a complaint is settled with a refund, the lowest manager whose limit covers the amount approves it, then Accounts pays it.",
    unit: "inr",
  },
];

/**
 * APPR-002 · The approval limits: an order's value, a quotation's discount and a complaint's
 * refund, per role —
 * company-wide, and a territory's own where one is set. Anyone signed in reads them; those
 * who may edit masters change one level at a time.
 */
export function ApprovalLimits(): React.JSX.Element {
  const query = useQuery(approvalThresholdsQueryOptions());
  const canEdit = useCan("masters", "edit");
  const [target, setTarget] = useState<LimitTarget | null>(null);

  return (
    <QueryView
      query={query}
      pending={<ApprovalLimitsSkeleton />}
      isEmpty={(rows) => rows.length === 0}
      empty={
        <Notice tone="warning">
          <p className="font-medium">No approval limits are set</p>
          <p className="text-muted-foreground">
            Until they are, orders and discounts can&apos;t find an approver. Ask the backend team
            to seed them.
          </p>
        </Notice>
      }
    >
      {(rows) => (
        <div className="flex flex-col gap-5">
          <Notice tone="info">
            <p>
              A change applies to orders submitted and discounts asked from then on. Each level
              stays above the one below.
              {canEdit ? null : " Only an administrator changes these."}
            </p>
          </Notice>
          <div className="grid items-start gap-4 lg:grid-cols-2">
            {LADDERS.map((ladder) => (
              <LadderCard
                key={ladder.docType}
                rows={rows}
                docType={ladder.docType}
                title={ladder.title}
                explain={ladder.explain}
                unit={ladder.unit}
                canEdit={canEdit}
                onEdit={setTarget}
              />
            ))}
          </div>
          <ApprovalLimitDialog
            rows={rows}
            target={target}
            onClose={() => {
              setTarget(null);
            }}
          />
        </div>
      )}
    </QueryView>
  );
}

interface LadderCardProps {
  rows: readonly Threshold[];
  docType: ThresholdDocType;
  title: string;
  explain: string;
  unit: Threshold["unit"];
  canEdit: boolean;
  onEdit: (target: LimitTarget) => void;
}

function LadderCard({
  rows,
  docType,
  title,
  explain,
  unit,
  canEdit,
  onEdit,
}: LadderCardProps): React.JSX.Element {
  const territories = overrideTerritories(rows, docType);
  return (
    <Card>
      <CardHeader className="flex flex-col gap-1">
        <CardTitle level={2}>{title}</CardTitle>
        <p className="text-sm text-muted-foreground">{explain}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Ladder
          label={`${title}, company-wide`}
          steps={ladderFor(rows, docType, null)}
          unit={unit}
          canEdit={canEdit}
          onEdit={(role) => {
            onEdit({ docType, role, territory: null });
          }}
        />
        {territories.map((territory) => (
          <div key={territory.id} className="flex flex-col gap-2">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
              {territory.name}
              <Badge variant="outline" size="sm">
                Own limits
              </Badge>
            </p>
            <Ladder
              label={`${title}, ${territory.name}`}
              steps={ladderFor(rows, docType, territory.id).filter((step) => step.row !== null)}
              unit={unit}
              canEdit={canEdit}
              onEdit={(role) => {
                onEdit({ docType, role, territory });
              }}
            />
            <p className="text-xs text-muted-foreground">
              Levels not listed use the company-wide limit.
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Ladder({
  label,
  steps,
  unit,
  canEdit,
  onEdit,
}: {
  label: string;
  steps: readonly LadderStep[];
  unit: Threshold["unit"];
  canEdit: boolean;
  onEdit: (role: LadderStep["role"]) => void;
}): React.JSX.Element {
  return (
    <ol
      aria-label={label}
      className="flex flex-col divide-y divide-border rounded-lg border border-border"
    >
      {steps.map((step, index) => (
        <li key={step.role} className="flex items-center justify-between gap-3 px-3 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <span
              aria-hidden="true"
              className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs text-muted-foreground tabular-nums"
            >
              {index + 1}
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-medium text-foreground">
                {limitRoleLabel(step.role)}
              </span>
              <span className="text-sm text-muted-foreground tabular-nums">
                {step.row === null ? "Not set" : formatLimit(step.row.maxAmount, unit)}
              </span>
            </div>
          </div>
          {canEdit ? (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Change the ${limitRoleLabel(step.role)} limit (${label})`}
              onClick={() => {
                onEdit(step.role);
              }}
            >
              <Icon icon={Edit02Icon} />
              Change
            </Button>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/** Mirrors ApprovalLimits: the notice and two ladders. */
export function ApprovalLimitsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading approval limits" className="flex flex-col gap-5">
      <Skeleton className="h-12 w-full rounded-lg" />
      <div className="grid items-start gap-4 lg:grid-cols-2">
        {[3, 5].map((count) => (
          <Card key={count}>
            <CardHeader className="flex flex-col gap-2">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-4 w-full" />
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {Array.from({ length: count }, (_, index) => (
                <Skeleton key={index} className="h-12 w-full rounded-lg" />
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
