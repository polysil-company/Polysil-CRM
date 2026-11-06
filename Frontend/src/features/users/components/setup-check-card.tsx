"use client";

import { CheckmarkCircle02Icon, Settings02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/session/hooks/use-session";
import { setupCheckQueryOptions } from "@/features/users/api/users.queries";
import type { SetupCheck } from "@/features/users/api/users.schemas";
import { isApiError } from "@/lib/api/errors";
import { formatCount } from "@/lib/format";

/** How many of a check's people show before "Show all". */
const FIRST_FEW = 5;

/**
 * ADMN-009 · The setup check on the admin dashboard (FS-082): what is set up wrong, each with
 * its count, why it matters and who to fix, linked to their page. Only for users.edit; a
 * 403 (the permission held for less than the whole company) shows nothing.
 */
export function SetupCheckCard(): React.JSX.Element | null {
  const mayEdit = useCan("users", "edit");
  const query = useQuery({ ...setupCheckQueryOptions(), enabled: mayEdit });

  if (!mayEdit) return null;
  if (query.status === "pending") return <SetupCheckSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 403) return null;
    return (
      <Card>
        <SetupHeader />
        <CardContent>
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        </CardContent>
      </Card>
    );
  }

  const open = query.data.checks.filter((check) => check.count > 0);
  if (query.data.ok || open.length === 0) {
    return (
      <p
        role="status"
        className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground"
      >
        <Icon icon={CheckmarkCircle02Icon} className="text-success" />
        Setup: nothing to fix. Everyone sits in an office with an area and a manager above them.
      </p>
    );
  }

  return (
    <Card>
      <SetupHeader count={open.reduce((sum, check) => sum + check.count, 0)} />
      <CardContent>
        <ul aria-label="Setup to fix" className="flex flex-col divide-y divide-border">
          {open.map((check) => (
            <SetupCheckRow key={check.code} check={check} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function SetupHeader({ count }: { count?: number }): React.JSX.Element {
  return (
    <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
      <div className="flex flex-col gap-0.5">
        <CardTitle className="flex items-center gap-2">
          <Icon icon={Settings02Icon} className="text-warning" />
          Setup to fix
        </CardTitle>
        <CardDescription>
          People and partners set up so that leads, dealers or approvals go astray.
        </CardDescription>
      </div>
      {count === undefined ? null : <Badge variant="warning">{formatCount(count)} to fix</Badge>}
    </CardHeader>
  );
}

function SetupCheckRow({ check }: { check: SetupCheck }): React.JSX.Element {
  const [all, setAll] = useState(false);
  const shown = all ? check.items : check.items.slice(0, FIRST_FEW);
  const hidden = check.items.length - shown.length;
  const beyond = check.count - check.items.length;
  const titleId = `setup-${check.code}`;

  return (
    <li aria-labelledby={titleId} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={titleId} className="text-sm font-medium text-foreground">
          {check.title}
        </h3>
        <Badge variant="warning">{formatCount(check.count)}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{check.why}</p>
      <ul aria-label={`Who to fix: ${check.title}`} className="flex flex-col gap-1">
        {shown.map((item) => (
          <li key={item.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <Link
              href={check.kind === "partner" ? `/partners/${item.id}` : `/users/${item.id}`}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {item.name}
            </Link>
            <span className="text-xs text-muted-foreground">{item.detail}</span>
          </li>
        ))}
      </ul>
      {hidden > 0 ? (
        <Button
          variant="ghost"
          size="sm"
          className="w-fit"
          onClick={() => {
            setAll(true);
          }}
        >
          Show all {formatCount(check.items.length)}
        </Button>
      ) : null}
      {all && beyond > 0 ? (
        <p className="text-xs text-muted-foreground">
          And {formatCount(beyond)} more; fix these first and the rest show up.
        </p>
      ) : null}
    </li>
  );
}

/** Mirrors the card: a header and two checks. */
export function SetupCheckSkeleton(): React.JSX.Element {
  return (
    <Card aria-hidden="true">
      <CardHeader className="flex-col gap-1.5">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </CardContent>
    </Card>
  );
}
