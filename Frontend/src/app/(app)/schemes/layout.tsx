import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { SchemesTabs } from "@/features/schemes/components/schemes-tabs";

/** Schemes · Credits, kept while the tabs change. The title sits in the top bar. */
export default function SchemesLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <PageContainer>
      <div className="flex flex-col gap-4">
        <SchemesTabs />
        {children}
      </div>
    </PageContainer>
  );
}
