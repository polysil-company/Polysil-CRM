import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { RouteDay } from "@/features/tracking/components/route-day";

export const metadata: Metadata = { title: "Route of a day" };

/** TRK-002 · One person's day on the map. */
export default async function RoutePage({
  params,
}: PageProps<"/team-map/[userId]">): Promise<React.JSX.Element> {
  const { userId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <RouteDay userId={userId} />
      </PageContainer>
    </PageTransition>
  );
}
