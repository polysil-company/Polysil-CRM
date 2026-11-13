import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { EditQuotation } from "@/features/quotations/components/quotation-builder-pages";

export const metadata: Metadata = { title: "Edit quotation" };

export default async function EditQuotationPage({
  params,
}: PageProps<"/quotations/[quotationId]/edit">): Promise<React.JSX.Element> {
  const { quotationId } = await params;

  return (
    <PageTransition>
      <section aria-label="Edit quotation" className="flex flex-col">
        <EditQuotation quotationId={quotationId} />
      </section>
    </PageTransition>
  );
}
