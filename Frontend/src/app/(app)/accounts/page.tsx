import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { AccountsQueue } from "@/features/orders/components/accounts-queue";

export const metadata: Metadata = { title: "Accounts queue" };

/** ACCT-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function AccountsQueuePage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <AccountsQueue />
      </PageContainer>
    </PageTransition>
  );
}
