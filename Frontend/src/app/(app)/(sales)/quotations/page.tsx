import { Invoice03Icon } from "@hugeicons/core-free-icons";
import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { EmptyState } from "@/components/patterns/empty-state";

export const metadata: Metadata = { title: "Quotations" };

// TODO(QUOT-001): build the quotations list on the same DataTable, QueryView and filter patterns as leads.
export default function QuotationsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Quotations" className="flex flex-1 flex-col">
        <EmptyState
          icon={Invoice03Icon}
          title="Quotations are the next module"
          description="Quote from a lead with type-based templates, versions and approvals."
          action={
            <code className="rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
              QUOT-001
            </code>
          }
          className="flex-1 rounded-xl border border-dashed border-border"
        />
      </section>
    </PageTransition>
  );
}
