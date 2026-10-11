"use client";

import type * as React from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PriceListsPanel } from "@/features/products/components/price-lists-panel";
import {
  ProductCatalogue,
  ProductCatalogueSkeleton,
} from "@/features/products/components/product-catalogue";
import { TaxRatesPanel } from "@/features/products/components/tax-rates-panel";
import {
  PRODUCT_MASTER_TABS,
  useProductMasterParams,
} from "@/features/products/hooks/use-product-master-params";
import { useCan } from "@/features/session/hooks/use-session";

/**
 * MSTR-004…006 · Products & prices: the catalogue, the price lists and the GST rates, one tab
 * each, the tab kept in the URL. Admin-Sales and the MD change them; everyone else reads.
 */
export function ProductMaster(): React.JSX.Element {
  const { tab, setTab } = useProductMasterParams();
  const canEditProducts = useCan("products", "edit");
  const canEditPricing = useCan("pricing", "edit");

  return (
    <Tabs
      value={tab}
      onValueChange={(next) => {
        const chosen = PRODUCT_MASTER_TABS.find((value) => value === next);
        if (chosen !== undefined) setTab(chosen);
      }}
      className="flex flex-col gap-5"
    >
      <TabsList aria-label="Product master" className="scrollbar-none overflow-x-auto">
        <TabsTrigger value="products">Products</TabsTrigger>
        <TabsTrigger value="price-lists">Price lists</TabsTrigger>
        <TabsTrigger value="tax-rates">Tax rates</TabsTrigger>
      </TabsList>
      <TabsContent value="products">
        <ProductCatalogue canEdit={canEditProducts} />
      </TabsContent>
      <TabsContent value="price-lists">
        <PriceListsPanel canEdit={canEditPricing} />
      </TabsContent>
      <TabsContent value="tax-rates">
        <TaxRatesPanel canEdit={canEditProducts} />
      </TabsContent>
    </Tabs>
  );
}

export function ProductMasterSkeleton(): React.JSX.Element {
  return <ProductCatalogueSkeleton />;
}
