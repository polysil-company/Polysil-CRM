import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ReportsHome } from "@/features/reports/components/reports-home";

export const metadata: Metadata = { title: "Reports" };

/** RPT-002 · A card per report the user may open. */
export default function ReportsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <ReportsHome />
      </PageContainer>
    </PageTransition>
  );
}
