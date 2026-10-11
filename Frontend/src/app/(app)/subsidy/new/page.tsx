import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { StartApplication } from "@/features/subsidy/components/start-application";

export const metadata: Metadata = { title: "Start a subsidy application" };

/** SUBS-004 · `?lead=` names the subsidised lead to forward. */
export default async function NewSubsidyApplicationPage({
  searchParams,
}: PageProps<"/subsidy/new">): Promise<React.JSX.Element> {
  const params = await searchParams;
  const lead = typeof params.lead === "string" && params.lead !== "" ? params.lead : null;
  return (
    <PageTransition>
      <StartApplication leadId={lead} />
    </PageTransition>
  );
}
