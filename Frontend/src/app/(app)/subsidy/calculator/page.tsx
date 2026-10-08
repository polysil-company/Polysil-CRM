import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { SubsidyCalculator } from "@/features/subsidy/components/subsidy-calculator";

export const metadata: Metadata = { title: "Subsidy calculator" };

/** SUBS-002 · The title and description sit in the top bar, from the navigation map. */
export default function SubsidyCalculatorPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <SubsidyCalculator />
      </PageContainer>
    </PageTransition>
  );
}
