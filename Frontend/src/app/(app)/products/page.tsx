import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ProductMaster } from "@/features/products/components/product-master";

export const metadata: Metadata = { title: "Products & prices" };

/** MSTR-004…006 · The title and description sit in the top bar, from the navigation map. */
export default function ProductsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <ProductMaster />
      </PageContainer>
    </PageTransition>
  );
}
