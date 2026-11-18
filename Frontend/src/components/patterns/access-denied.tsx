import { LockIcon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { buttonVariants } from "@/components/ui/button-variants";

export interface AccessDeniedProps {
  className?: string;
}

/**
 * APP-006 · A page the signed-in user may not open. It replaces the whole page rather than
 * sitting under its header and filters, and carries no error reference: nothing failed, so
 * there is nothing for support to trace (walk F-17).
 */
export function AccessDenied({ className }: AccessDeniedProps): React.JSX.Element {
  return (
    <EmptyState
      icon={LockIcon}
      level={2}
      title="You don't have access to this page"
      description="Ask your manager or an admin if you need it."
      action={
        <Link href="/dashboard" className={buttonVariants({ variant: "outline" })}>
          Back to the dashboard
        </Link>
      }
      {...(className === undefined ? {} : { className })}
    />
  );
}
