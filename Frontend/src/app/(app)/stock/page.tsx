import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { StockPage } from "@/features/stock/components/stock-page";

export const metadata: Metadata = { title: "Stock" };

/** MSTR-014 · The title and description sit in the top bar (APP-005). */
export default function StockRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <StockPage />
      </PageContainer>
    </PageTransition>
  );
}
