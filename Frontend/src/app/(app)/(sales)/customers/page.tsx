import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { CustomersSearch } from "@/features/customers/components/customers-search";

export const metadata: Metadata = { title: "Customers" };

/** LEAD-016 · Find a customer. The title and description sit in the top bar, from the navigation map. */
export default function CustomersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Customers" className="flex flex-col">
        <CustomersSearch />
      </section>
    </PageTransition>
  );
}
