import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { TrackingSettings } from "@/features/tracking/components/tracking-settings";

export const metadata: Metadata = { title: "Tracking settings" };

/** TRK-006, TRK-007 · The title and description sit in the top bar, from the navigation map. */
export default function TrackingSettingsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <TrackingSettings />
      </PageContainer>
    </PageTransition>
  );
}
