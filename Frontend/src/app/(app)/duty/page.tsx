import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { DutyScreen } from "@/features/tracking/components/duty-screen";

export const metadata: Metadata = { title: "Duty" };

/** TRK-008 · Shown inside the Android app; a browser explains where Duty lives. */
export default function DutyPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <DutyScreen />
      </PageContainer>
    </PageTransition>
  );
}
