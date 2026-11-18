import type * as React from "react";

import { ProductMasterSkeleton } from "@/features/products/components/product-master";

export default function ProductsLoading(): React.JSX.Element {
  return <ProductMasterSkeleton />;
}
