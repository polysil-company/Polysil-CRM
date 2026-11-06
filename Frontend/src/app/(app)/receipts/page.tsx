import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ReceiptsList } from "@/features/payments/components/receipts-list";

export const metadata: Metadata = { title: "Receipts" };

/** ACCT-003 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function ReceiptsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <ReceiptsList />
      </PageContainer>
    </PageTransition>
  );
}
