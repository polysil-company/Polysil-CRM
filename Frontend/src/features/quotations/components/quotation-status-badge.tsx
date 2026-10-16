import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { QuotationStatus } from "@/features/quotations/api/quotations.schemas";
import {
  QUOTATION_STATUS_BADGE,
  QUOTATION_STATUS_LABELS,
} from "@/features/quotations/lib/quotation-labels";

export interface QuotationStatusBadgeProps {
  status: QuotationStatus;
  /** A discount request on this draft waits for a manager: the draft can't be sent yet. */
  awaitingApproval?: boolean;
  className?: string;
}

/**
 * QUOT-001 · A quotation's status, as a labelled chip. A draft whose discount waits for a
 * manager reads "Awaiting approval", so nobody chases a draft that is not theirs to send.
 */
export function QuotationStatusBadge({
  status,
  awaitingApproval = false,
  className,
}: QuotationStatusBadgeProps): React.JSX.Element {
  if (status === "draft" && awaitingApproval) {
    return (
      <Badge variant="warning" dot className={className}>
        Awaiting approval
      </Badge>
    );
  }
  return (
    <Badge variant={QUOTATION_STATUS_BADGE[status]} dot className={className}>
      {QUOTATION_STATUS_LABELS[status]}
    </Badge>
  );
}
