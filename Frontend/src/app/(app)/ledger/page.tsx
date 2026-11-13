import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { MyLedger } from "@/features/payments/components/my-ledger";

export const metadata: Metadata = { title: "My ledger" };

/** ACCT-005 · A partner user's own ledger. The title sits in the top bar (APP-005). */
export default function LedgerPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <MyLedger />
      </PageContainer>
    </PageTransition>
  );
}
