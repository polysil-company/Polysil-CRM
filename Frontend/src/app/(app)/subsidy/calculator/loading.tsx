import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { SubsidyCalculatorSkeleton } from "@/features/subsidy/components/subsidy-calculator";

export default function SubsidyCalculatorLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <SubsidyCalculatorSkeleton />
    </PageContainer>
  );
}
