import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { PageHeader } from "@/components/patterns/page-header";
import { SalesTabs } from "@/features/leads/components/sales-tabs";

/** Shared header and tabs for Leads · Quotations · Sales orders. Persists while tabs change. */
export default function SalesLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <PageContainer fill>
      <PageHeader title="Sales" description="Leads, quotations and orders in your territory.">
        <SalesTabs />
      </PageHeader>
      {children}
    </PageContainer>
  );
}
