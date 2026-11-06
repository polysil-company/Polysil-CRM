import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { QuotationSubsidyStep } from "@/features/quotations/components/quotation-subsidy";

export const metadata: Metadata = { title: "Quotation subsidy" };

export default async function QuotationSubsidyPage({
  params,
}: PageProps<"/quotations/[quotationId]/subsidy">): Promise<React.JSX.Element> {
  const { quotationId } = await params;

  return (
    <PageTransition>
      <section aria-label="Quotation subsidy" className="flex flex-col">
        <QuotationSubsidyStep quotationId={quotationId} />
      </section>
    </PageTransition>
  );
}
