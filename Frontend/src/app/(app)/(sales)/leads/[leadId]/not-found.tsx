import { UserMultiple02Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { buttonVariants } from "@/components/ui/button-variants";

export default function LeadNotFound(): React.JSX.Element {
  return (
    <EmptyState
      icon={UserMultiple02Icon}
      title="Lead not found"
      description="It may have been removed, merged into another lead, or reassigned outside your territory."
      action={
        <Link href="/leads" className={buttonVariants({ variant: "outline" })}>
          Back to all leads
        </Link>
      }
      className="rounded-xl border border-dashed border-border"
    />
  );
}
