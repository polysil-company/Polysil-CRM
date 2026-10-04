"use client";

import { Add01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import type { ComplaintListParams } from "@/features/complaints/api/complaints.schemas";
import { useCan } from "@/features/session/hooks/use-session";

import { ComplaintRows } from "./complaints-list";

function paramsFor(about: { leadId: string } | { orderId: string }): ComplaintListParams {
  return {
    status: [],
    severity: null,
    typeId: null,
    q: "",
    breached: false,
    noOwner: false,
    awaitingMe: false,
    leadId: "leadId" in about ? about.leadId : null,
    orderId: "orderId" in about ? about.orderId : null,
  };
}

/**
 * CMPL-001, CMPL-003 · The complaints about one lead or one order, newest first, with
 * "Raise a complaint" about it for whoever may raise one (not on a merged lead). Shown to
 * whoever may see complaints.
 */
export function RelatedComplaints({
  about,
  readOnly = false,
}: {
  about: { leadId: string } | { orderId: string };
  /** A merged lead takes no new complaints. */
  readOnly?: boolean;
}): React.JSX.Element | null {
  const canView = useCan("complaints");
  const canCreate = useCan("complaints", "create");
  if (!canView) return null;
  const query =
    "leadId" in about
      ? `lead=${encodeURIComponent(about.leadId)}`
      : `order=${encodeURIComponent(about.orderId)}`;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Complaints</CardTitle>
          <CardDescription>
            {"leadId" in about ? "About this lead" : "About this order"}
          </CardDescription>
        </div>
        {canCreate && !readOnly ? (
          <Link
            href={`/complaints/new?${query}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <Icon icon={Add01Icon} />
            Raise a complaint
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        <ComplaintRows params={paramsFor(about)} filtered={false} />
      </CardContent>
    </Card>
  );
}
