import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { QuotationStatus } from "@/features/quotations/api/quotations.schemas";
import {
  QUOTATION_STATUS_BADGE,
  QUOTATION_STATUS_LABELS,
} from "@/features/quotations/lib/quotation-labels";

export interface QuotationStatusBadgeProps {
  status: QuotationStatus;
  className?: string;
}

/** QUOT-001 · A quotation's status, as a labelled chip. */
export function QuotationStatusBadge({
  status,
  className,
}: QuotationStatusBadgeProps): React.JSX.Element {
  return (
    <Badge variant={QUOTATION_STATUS_BADGE[status]} dot className={className}>
      {QUOTATION_STATUS_LABELS[status]}
    </Badge>
  );
}
