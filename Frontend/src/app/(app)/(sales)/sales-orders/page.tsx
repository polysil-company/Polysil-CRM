import { PackageIcon } from "@hugeicons/core-free-icons";
import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { EmptyState } from "@/components/patterns/empty-state";

export const metadata: Metadata = { title: "Sales orders" };

// TODO(SO-001): build the sales orders list on the same DataTable, QueryView and filter patterns as leads.
export default function SalesOrdersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Sales orders" className="flex flex-1 flex-col">
        <EmptyState
          icon={PackageIcon}
          title="Sales orders are coming soon"
          description="Orders created from won leads or directly, with dispatch details and payment terms."
          action={
            <code className="rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
              SO-001
            </code>
          }
          className="flex-1 rounded-xl border border-dashed border-border"
        />
      </section>
    </PageTransition>
  );
}
