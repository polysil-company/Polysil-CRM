import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { EditScheme } from "@/features/schemes/components/scheme-editors";

export const metadata: Metadata = { title: "Edit scheme" };

/** SCHM-002 */
export default async function EditSchemePage({
  params,
}: PageProps<"/schemes/[schemeId]/edit">): Promise<React.JSX.Element> {
  const { schemeId } = await params;
  return (
    <PageTransition>
      <EditScheme schemeId={schemeId} />
    </PageTransition>
  );
}
