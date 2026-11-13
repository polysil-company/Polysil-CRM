"use client";

import { ArrowLeft01Icon, PencilEdit02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { usePatchScheme } from "@/features/schemes/api/schemes.mutations";
import {
  schemeDetailQueryOptions,
  standingQueryOptions,
} from "@/features/schemes/api/schemes.queries";
import type { Scheme } from "@/features/schemes/api/schemes.schemas";
import {
  benefitText,
  conditionText,
  formatFigure,
  PERIOD_LABELS,
  SCHEME_STATE_LABELS,
  SCHEME_TYPE_DESCRIPTIONS,
  SCHEME_TYPE_LABELS,
  schemeState,
  validityText,
} from "@/features/schemes/lib/scheme-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatCalendarDay, formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { PartnerSearchPicker, type PickedRecord } from "./record-pickers";
import { TargetsSummary } from "./scheme-targets";
import { STATE_BADGE } from "./schemes-list";

const log = createLogger({
  file: "features/schemes/components/scheme-detail.tsx",
  dataId: "SCHM-001",
});

/** SCHM-001 · A scheme: its terms, who it's for, and, for a period scheme, the standing. */
export function SchemeDetail({ schemeId }: { schemeId: string }): React.JSX.Element {
  const query = useQuery(schemeDetailQueryOptions(schemeId));
  if (isApiError(query.error) && query.error.status === 404) notFound();
  return (
    <QueryView query={query} pending={<SchemeDetailSkeleton />} isEmpty={() => false} empty={null}>
      {(scheme) => <SchemeView scheme={scheme} />}
    </QueryView>
  );
}

function SchemeView({ scheme }: { scheme: Scheme }): React.JSX.Element {
  const staff = useIsStaff();
  const canEdit = useCan("schemes", "edit");
  const state = schemeState(scheme);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link
          href="/schemes"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          <Icon icon={ArrowLeft01Icon} />
          All schemes
        </Link>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-semibold text-foreground">{scheme.name}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground">{scheme.code}</span>
              <Badge variant="neutral">{SCHEME_TYPE_LABELS[scheme.type]}</Badge>
              <Badge variant={STATE_BADGE[state]}>{SCHEME_STATE_LABELS[state]}</Badge>
            </div>
          </div>
          {canEdit ? (
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href={`/schemes/${scheme.id}/edit`}
                className={buttonVariants({ variant: "outline" })}
              >
                <Icon icon={PencilEdit02Icon} />
                {scheme.used ? "Change the end date" : "Edit"}
              </Link>
              <ActiveSwitch scheme={scheme} />
            </div>
          ) : null}
        </div>
      </div>

      {scheme.used && staff ? (
        <Notice tone="info">
          This scheme has given benefits, so only its end date and whether it&apos;s switched on can
          change. To change its terms, end it and create a new one.
        </Notice>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle level={3}>Terms</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <Term label="What it gives">{benefitText(scheme)}</Term>
            <Term label="Qualifies">{conditionText(scheme)}</Term>
            <Term label="Type">
              {SCHEME_TYPE_LABELS[scheme.type]}
              <span className="block text-xs text-muted-foreground">
                {SCHEME_TYPE_DESCRIPTIONS[scheme.type]}
              </span>
            </Term>
            {scheme.period === null ? null : (
              <Term label="Runs by">{PERIOD_LABELS[scheme.period]}</Term>
            )}
            <Term label="Dates">{validityText(scheme)}</Term>
            {staff ? (
              <Term label="Beside other schemes">
                Priority {formatNumber(scheme.priority)} ·{" "}
                {scheme.stackable ? "can apply beside another discount" : "applies alone"}
              </Term>
            ) : null}
            {scheme.description === null ? null : (
              <Term label="About it" className="sm:col-span-2">
                {scheme.description}
              </Term>
            )}
          </dl>
        </CardContent>
      </Card>

      {staff ? (
        <Card>
          <CardHeader>
            <CardTitle level={3}>Who it&apos;s for</CardTitle>
          </CardHeader>
          <CardContent>
            <TargetsSummary targets={scheme.targets} />
          </CardContent>
        </Card>
      ) : null}

      {scheme.type === "period" ? <StandingCard scheme={scheme} staff={staff} /> : null}
    </div>
  );
}

function Term({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}

/** SCHM-002 · Switch a scheme off (no new benefits; credits stay usable) or back on. */
function ActiveSwitch({ scheme }: { scheme: Scheme }): React.JSX.Element {
  const patch = usePatchScheme();
  const idempotency = useIdempotencyKey();
  const action = useAsyncAction({
    action: () => {
      const body = { is_active: !scheme.isActive };
      return patch.mutateAsync({
        schemeId: scheme.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleToggleScheme",
    dataId: "SCHM-002",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(
        saved.isActive
          ? "Scheme switched on"
          : "Scheme switched off. Credits already earned stay usable.",
      );
    },
    onError: (error) => {
      toast.error("Not changed", { description: toUserFacingError(error).description });
    },
  });
  return (
    <Button
      variant="outline"
      state={action.state}
      loadingLabel={scheme.isActive ? "Switching off…" : "Switching on…"}
      successLabel="Done"
      errorLabel="Not changed"
      onClick={() => {
        void action.run();
      }}
    >
      {scheme.isActive ? "Switch off" : "Switch on"}
    </Button>
  );
}

/**
 * SCHM-003 · A period scheme's standing: what has been delivered so far this month or quarter
 * against the target. A partner user sees its own; staff pick the partner.
 */
function StandingCard({ scheme, staff }: { scheme: Scheme; staff: boolean }): React.JSX.Element {
  const [partner, setPartner] = useState<PickedRecord | null>(null);
  const ready = !staff || partner !== null;
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>{staff ? "A dealer's standing" : "Where you stand"}</CardTitle>
          <CardDescription>
            What has been delivered so far this {scheme.period === "quarter" ? "quarter" : "month"},
            against the target.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {staff ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="standing-partner" className="text-sm font-medium text-foreground">
              Partner
            </label>
            <PartnerSearchPicker
              id="standing-partner"
              placeholder="Search a partner to see where it stands"
              onPick={setPartner}
            />
            {partner === null ? null : (
              <p className="text-sm text-muted-foreground">
                Showing {partner.name} ({partner.note.toLowerCase()}).
              </p>
            )}
          </div>
        ) : null}
        {ready ? <Standing schemeId={scheme.id} partnerId={partner?.id ?? null} /> : null}
      </CardContent>
    </Card>
  );
}

function Standing({
  schemeId,
  partnerId,
}: {
  schemeId: string;
  partnerId: string | null;
}): React.JSX.Element {
  const query = useQuery(standingQueryOptions(schemeId, partnerId));
  if (query.status === "pending") return <Skeleton className="h-16 w-full" />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) {
      return <p className="text-sm text-muted-foreground">The scheme hasn&apos;t started yet.</p>;
    }
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const standing = query.data;
  const achieved = Number(standing.achieved);
  const min = Number(standing.min);
  const short = Math.max(0, min - achieved);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-foreground">
        {formatCalendarDay(standing.periodStart)} to {formatCalendarDay(standing.periodEnd)}:{" "}
        <span className="font-semibold tabular-nums">
          {formatFigure(standing.metric, standing.achieved)}
        </span>{" "}
        of {formatFigure(standing.metric, standing.min)}
        {standing.max === null ? "" : ` (up to ${formatFigure(standing.metric, standing.max)})`}
      </p>
      <ProportionBar
        value={achieved}
        max={min > 0 ? min : 1}
        tone={standing.qualifies ? "success" : "primary"}
      />
      <p className={standing.qualifies ? "text-sm text-success" : "text-sm text-muted-foreground"}>
        {standing.qualifies
          ? "The target is met for this period."
          : `${formatFigure(standing.metric, String(short))} to go.`}
      </p>
    </div>
  );
}

function SchemeDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading scheme" className="flex flex-col gap-4">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-24 w-full rounded-xl" />
    </div>
  );
}
