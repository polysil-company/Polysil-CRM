import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { NewDirectOrder } from "@/features/orders/components/order-builder-pages";

export const metadata: Metadata = { title: "New order" };

/** SO-005 · `?lead=<id>` names the lead the order is for; without it the order starts afresh. */
export default async function NewOrderPage({
  searchParams,
}: PageProps<"/sales-orders/new">): Promise<React.JSX.Element> {
  const { lead } = await searchParams;

  return (
    <PageTransition>
      <section aria-label="New order" className="flex flex-col">
        <NewDirectOrder leadId={typeof lead === "string" && lead !== "" ? lead : null} />
      </section>
    </PageTransition>
  );
}
