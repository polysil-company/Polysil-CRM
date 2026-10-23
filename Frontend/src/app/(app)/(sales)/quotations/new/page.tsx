import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { NewQuotation } from "@/features/quotations/components/quotation-builder-pages";

export const metadata: Metadata = { title: "New quotation" };

/** `?lead=<id>` names the lead the quotation is for. */
export default async function NewQuotationPage({
  searchParams,
}: PageProps<"/quotations/new">): Promise<React.JSX.Element> {
  const { lead } = await searchParams;

  return (
    <PageTransition>
      <section aria-label="New quotation" className="flex flex-col">
        <NewQuotation leadId={typeof lead === "string" && lead !== "" ? lead : null} />
      </section>
    </PageTransition>
  );
}
