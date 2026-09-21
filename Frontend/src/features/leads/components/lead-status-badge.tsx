import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { LeadStatus } from "@/features/leads/api/leads.schemas";
import { LEAD_STATUS_BADGE, LEAD_STATUS_LABELS } from "@/features/leads/lib/lead-labels";

export interface LeadStatusBadgeProps {
  status: LeadStatus;
  className?: string;
}

export function LeadStatusBadge({ status, className }: LeadStatusBadgeProps): React.JSX.Element {
  return (
    <Badge variant={LEAD_STATUS_BADGE[status]} dot className={className}>
      {LEAD_STATUS_LABELS[status]}
    </Badge>
  );
}
