import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import {
  SubsidyCalculator,
  SubsidyCalculatorSkeleton,
} from "@/features/subsidy/components/subsidy-calculator";

export const metadata: Metadata = { title: "Subsidy calculator" };

/** SUBS-002 · The system tab is read from the URL, which needs a Suspense boundary. */
export default function SubsidyCalculatorPage(): React.JSX.Element {
  return (
    <PageTransition>
      <Suspense fallback={<SubsidyCalculatorSkeleton />}>
        <SubsidyCalculator />
      </Suspense>
    </PageTransition>
  );
}
