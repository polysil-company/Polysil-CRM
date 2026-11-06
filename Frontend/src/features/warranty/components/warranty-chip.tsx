import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import type { ComplaintLineWarranty } from "@/features/warranty/api/warranty.schemas";
import {
  CLAIM_WARRANTY_BADGE,
  CLAIM_WARRANTY_LABELS,
} from "@/features/warranty/lib/warranty-labels";

/**
 * CMPL-011 · A complaint line's warranty: in or out, until when, and whether the period ran from
 * the dispatch or from the supply date typed on the complaint. Out of warranty blocks nothing.
 */
export function ComplaintWarranty({
  warranty,
}: {
  warranty: ComplaintLineWarranty | null;
}): React.JSX.Element | null {
  if (warranty === null) return null;
  const until =
    warranty.end === null
      ? null
      : warranty.status === "in_warranty"
        ? `until ${formatBusinessDay(warranty.end)}`
        : `ended ${formatBusinessDay(warranty.end)}`;
  const basis =
    warranty.basis === "dispatch"
      ? "from the dispatch"
      : warranty.basis === "supply_date"
        ? "from the supply date"
        : null;
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <Badge variant={CLAIM_WARRANTY_BADGE[warranty.status]} size="sm">
        {CLAIM_WARRANTY_LABELS[warranty.status]}
      </Badge>
      {[until, basis].filter((part) => part !== null).join(", ")}
    </span>
  );
}
