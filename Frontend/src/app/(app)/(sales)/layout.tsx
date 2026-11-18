import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { SalesTabs } from "@/features/leads/components/sales-tabs";

/**
 * Shared tabs for Leads · Quotations · Sales orders. Persists while tabs change.
 * The page title and description sit in the top bar (APP-005).
 */
export default function SalesLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <PageContainer fill>
      <SalesTabs />
      {children}
    </PageContainer>
  );
}
