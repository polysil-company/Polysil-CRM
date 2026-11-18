import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { CustomerDetail } from "@/features/customers/components/customer-detail";

export const metadata: Metadata = { title: "Customer" };

/** LEAD-017 · One customer. */
export default async function CustomerPage({
  params,
}: PageProps<"/customers/[customerId]">): Promise<React.JSX.Element> {
  const { customerId } = await params;
  return (
    <PageTransition>
      <section aria-label="Customer" className="flex flex-col">
        <CustomerDetail customerId={customerId} />
      </section>
    </PageTransition>
  );
}
