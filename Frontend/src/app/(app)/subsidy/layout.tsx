import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { SubsidyTabs } from "@/features/subsidy/components/subsidy-tabs";

/** Applications · Calculator, kept while the tabs change. The title sits in the top bar. */
export default function SubsidyLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <PageContainer>
      <div className="flex flex-col gap-4">
        <SubsidyTabs />
        {children}
      </div>
    </PageContainer>
  );
}
