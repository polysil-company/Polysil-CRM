import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import {
  SubsidyCalculator,
  SubsidyCalculatorSkeleton,
} from "@/features/subsidy/components/subsidy-calculator";

export const metadata: Metadata = { title: "Subsidy calculator" };

/**
 * SUBS-002 · The title and description sit in the top bar, from the navigation map. The system
 * tab is read from the URL, which needs a Suspense boundary during prerendering.
 */
export default function SubsidyCalculatorPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <Suspense fallback={<SubsidyCalculatorSkeleton />}>
          <SubsidyCalculator />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
