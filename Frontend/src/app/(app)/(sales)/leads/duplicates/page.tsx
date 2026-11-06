import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { DuplicateReview } from "@/features/leads/components/duplicate-review";

export const metadata: Metadata = { title: "Possible duplicates" };

/** LEAD-012 · The duplicate review queue. */
export default function DuplicatesPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Possible duplicates" className="flex flex-col">
        <DuplicateReview />
      </section>
    </PageTransition>
  );
}
