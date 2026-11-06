import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { TeamMap } from "@/features/tracking/components/team-map";

export const metadata: Metadata = { title: "Team map" };

/** TRK-001 · The title and description sit in the top bar, from the navigation map. */
export default function TeamMapPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <TeamMap />
      </PageContainer>
    </PageTransition>
  );
}
