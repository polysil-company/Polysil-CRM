import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { MyVisits } from "@/features/tracking/components/my-visits";

export const metadata: Metadata = { title: "Visits" };

/** TRK-003 … TRK-005 · The title and description sit in the top bar, from the navigation map. */
export default function VisitsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <MyVisits />
      </PageContainer>
    </PageTransition>
  );
}
