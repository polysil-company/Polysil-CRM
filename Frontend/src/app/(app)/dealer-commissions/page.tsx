import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { CommissionsList } from "@/features/commission/components/commissions-list";

export const metadata: Metadata = { title: "Dealer commissions" };

/** SUBS-017 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function DealerCommissionsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <CommissionsList />
      </PageContainer>
    </PageTransition>
  );
}
