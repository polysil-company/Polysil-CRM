import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { LEAD_STAGE_BADGE, LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";

export interface LeadStageBadgeProps {
  stage: LeadStage;
  className?: string;
}

export function LeadStageBadge({ stage, className }: LeadStageBadgeProps): React.JSX.Element {
  return (
    <Badge variant={LEAD_STAGE_BADGE[stage]} dot className={className}>
      {LEAD_STAGE_LABELS[stage]}
    </Badge>
  );
}
