import type * as React from "react";

import { QuotationDetailSkeleton } from "@/features/quotations/components/quotation-detail";

export default function QuotationDetailLoading(): React.JSX.Element {
  return <QuotationDetailSkeleton />;
}
