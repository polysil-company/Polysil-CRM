import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { QuotationDetail } from "@/features/quotations/components/quotation-detail";

export const metadata: Metadata = { title: "Quotation" };

export default async function QuotationDetailPage({
  params,
}: PageProps<"/quotations/[quotationId]">): Promise<React.JSX.Element> {
  const { quotationId } = await params;

  return (
    <PageTransition>
      <section aria-label="Quotation" className="flex flex-col">
        <QuotationDetail quotationId={quotationId} />
      </section>
    </PageTransition>
  );
}
