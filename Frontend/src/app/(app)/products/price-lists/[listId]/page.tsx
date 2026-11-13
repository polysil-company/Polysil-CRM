import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PriceListSheet } from "@/features/products/components/price-list-sheet";

export const metadata: Metadata = { title: "Price list" };

/** MSTR-006 · One price list and its rate sheet. */
export default async function PriceListPage({
  params,
}: PageProps<"/products/price-lists/[listId]">): Promise<React.JSX.Element> {
  const { listId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <PriceListSheet listId={listId} />
      </PageContainer>
    </PageTransition>
  );
}
