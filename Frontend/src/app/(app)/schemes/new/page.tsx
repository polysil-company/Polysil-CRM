import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { NewScheme } from "@/features/schemes/components/scheme-editors";

export const metadata: Metadata = { title: "New scheme" };

/** SCHM-002 */
export default function NewSchemePage(): React.JSX.Element {
  return (
    <PageTransition>
      <NewScheme />
    </PageTransition>
  );
}
