"use client";

import { Add01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { applicationListQueryOptions } from "@/features/subsidy/api/subsidy-applications.queries";
import type { ApplicationListParams } from "@/features/subsidy/api/subsidy-applications.schemas";
import { cannotStartReason } from "@/features/subsidy/lib/application-labels";

import { ApplicationRows } from "./applications-list";

/**
 * SUBS-004, SUBS-005 · A subsidised lead's application, with "Start subsidy application" when
 * the lead can start one and has none in progress. Staff who see subsidy only; a lead that
 * isn't subsidised and never had an application shows nothing.
 */
export function LeadSubsidy({ lead }: { lead: Lead }): React.JSX.Element | null {
  const { data: session } = useSession();
  const canView = useCan("subsidy");
  const canCreate = useCan("subsidy", "create");
  const canEdit = useCan("subsidy", "edit");
  const staff = session?.userType === "staff";
  const params: ApplicationListParams = { status: null, stage: null, q: "", leadId: lead.id };
  const query = useInfiniteQuery({
    ...applicationListQueryOptions(params),
    enabled: canView && staff,
  });
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const live = rows.some((row) => row.status !== "cancelled");

  if (!canView || !staff) return null;
  if (lead.type !== "subsidised" && rows.length === 0) return null;
  const startable =
    (canCreate || canEdit) && !live && query.isSuccess && cannotStartReason(lead) === null;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Subsidy application</CardTitle>
          <CardDescription>
            Through the scheme&apos;s stages until every payment is in
          </CardDescription>
        </div>
        {startable ? (
          <Link
            href={`/subsidy/new?lead=${encodeURIComponent(lead.id)}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <Icon icon={Add01Icon} />
            Start subsidy application
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        <ApplicationRows
          params={params}
          filtered={false}
          emptyMessage={
            cannotStartReason(lead) ?? "No application yet. Start one when the farmer is ready."
          }
        />
      </CardContent>
    </Card>
  );
}
