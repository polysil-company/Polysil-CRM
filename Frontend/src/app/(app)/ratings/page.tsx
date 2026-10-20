import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { RatingsPage } from "@/features/ratings/components/ratings-page";

export const metadata: Metadata = { title: "Ratings" };

/** RATE-002, RATE-003 · The title and description sit in the top bar, from the navigation map. */
export default function RatingsRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <RatingsPage />
      </PageContainer>
    </PageTransition>
  );
}
