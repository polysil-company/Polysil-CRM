import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { SchemeDetail } from "@/features/schemes/components/scheme-detail";

export const metadata: Metadata = { title: "Scheme" };

/** SCHM-001 */
export default async function SchemePage({
  params,
}: PageProps<"/schemes/[schemeId]">): Promise<React.JSX.Element> {
  const { schemeId } = await params;
  return (
    <PageTransition>
      <SchemeDetail schemeId={schemeId} />
    </PageTransition>
  );
}
