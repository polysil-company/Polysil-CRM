"use client";

import { Invoice03Icon, LockIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { buttonVariants } from "@/components/ui/button-variants";
import { Skeleton } from "@/components/ui/skeleton";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import { quotationDetailQueryOptions } from "@/features/quotations/api/quotations.queries";
import { quotationBlockedReason, quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";

import { QuotationBuilder } from "./quotation-builder";

const FRAME = "rounded-xl border border-dashed border-border";

/** QUOT-004 · A new draft for `leadId`, once the lead may be quoted and the user may create. */
export function NewQuotation({ leadId }: { leadId: string | null }): React.JSX.Element {
  const canCreate = useCan("quotations", "create");
  const session = useSession();
  const lead = useQuery({ ...leadDetailQueryOptions(leadId ?? ""), enabled: leadId !== null });

  if (leadId === null) {
    return (
      <EmptyState
        icon={Invoice03Icon}
        title="Start from a lead"
        description="A quotation belongs to a lead. Open a qualified lead and choose New quotation."
        action={
          <Link href="/leads" className={buttonVariants({ variant: "outline" })}>
            Go to leads
          </Link>
        }
        className={FRAME}
      />
    );
  }
  if (session.isSuccess && !canCreate) {
    return <NoAccess what="make quotations" />;
  }
  if (lead.status === "error" && isApiError(lead.error) && lead.error.status === 404) {
    return (
      <EmptyState
        icon={Invoice03Icon}
        title="Lead not found"
        description="It may have been removed, merged, or reassigned outside your territory."
        action={
          <Link href="/leads" className={buttonVariants({ variant: "outline" })}>
            Back to all leads
          </Link>
        }
        className={FRAME}
      />
    );
  }
  return (
    <QueryView query={lead} pending={<BuilderSkeleton />} isEmpty={() => false} empty={null}>
      {(loaded) => {
        const blocked = quotationBlockedReason(loaded.stage);
        return blocked === null ? (
          <QuotationBuilder source={{ mode: "create", lead: loaded }} />
        ) : (
          <EmptyState
            icon={Invoice03Icon}
            title={`${loaded.customerName} can't be quoted yet`}
            description={`${blocked}. Quotations are made for qualified leads.`}
            action={
              <Link href={`/leads/${loaded.id}`} className={buttonVariants({ variant: "outline" })}>
                Back to the lead
              </Link>
            }
            className={FRAME}
          />
        );
      }}
    </QueryView>
  );
}

/** QUOT-004 · Edit a draft. A quotation that was sent is never edited — it is revised. */
export function EditQuotation({ quotationId }: { quotationId: string }): React.JSX.Element {
  const canEdit = useCan("quotations", "edit");
  const session = useSession();
  const quotation = useQuery(quotationDetailQueryOptions(quotationId));

  if (session.isSuccess && !canEdit) {
    return <NoAccess what="edit quotations" />;
  }
  if (
    quotation.status === "error" &&
    isApiError(quotation.error) &&
    quotation.error.status === 404
  ) {
    return (
      <EmptyState
        icon={Invoice03Icon}
        title="Quotation not found"
        description="It may have been a draft that was deleted, or it belongs to a lead outside your territory."
        action={
          <Link href="/quotations" className={buttonVariants({ variant: "outline" })}>
            Back to all quotations
          </Link>
        }
        className={FRAME}
      />
    );
  }
  return (
    <QueryView query={quotation} pending={<BuilderSkeleton />} isEmpty={() => false} empty={null}>
      {(loaded) =>
        loaded.status === "draft" ? (
          <QuotationBuilder source={{ mode: "edit", quotation: loaded }} />
        ) : (
          <EmptyState
            icon={LockIcon}
            title={`${quotationTitle(loaded)} was sent`}
            description="A sent quotation keeps its figures. To change them, revise it into a new version."
            action={
              <Link
                href={`/quotations/${loaded.id}`}
                className={buttonVariants({ variant: "outline" })}
              >
                Open the quotation
              </Link>
            }
            className={FRAME}
          />
        )
      }
    </QueryView>
  );
}

function NoAccess({ what }: { what: string }): React.JSX.Element {
  return (
    <EmptyState
      icon={LockIcon}
      title="You don't have access to this"
      description={`Your role cannot ${what}. Ask your manager or an admin if you need to.`}
      className={FRAME}
    />
  );
}

/** Mirrors the builder: heading, items with one row, customer card and the summary. */
export function BuilderSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the quotation builder" className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-5 w-80" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Skeleton className="h-56 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    </div>
  );
}
