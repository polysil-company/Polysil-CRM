import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { CompanySettings } from "@/features/settings/components/company-settings";

export const metadata: Metadata = { title: "Company settings" };

/** ADMN-007 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function CompanySettingsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <CompanySettings />
      </PageContainer>
    </PageTransition>
  );
}
