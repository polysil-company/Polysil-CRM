"use client";

import { Invoice03Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { DealerRatingCard } from "@/features/ratings/components/dealer-rating";
import { useSession } from "@/features/session/hooks/use-session";

import { PartnerLedgerCard } from "./partner-ledger";

/** ACCT-005 · The signed-in partner's own ledger; staff have no ledger of their own. */
export function MyLedger(): React.JSX.Element | null {
  const session = useSession();
  if (session.status === "pending") return <Skeleton className="h-64 w-full rounded-xl" />;
  const partner = session.data?.partner ?? null;
  if (partner === null) {
    return (
      <EmptyState
        icon={Invoice03Icon}
        title="No ledger for this account"
        description="A ledger belongs to a dealer, distributor or sub-dealer. Open a partner to see theirs."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <DealerRatingCard partnerId={partner.id} title="Your rating" />
      <PartnerLedgerCard partnerId={partner.id} title="Your ledger" />
    </div>
  );
}
