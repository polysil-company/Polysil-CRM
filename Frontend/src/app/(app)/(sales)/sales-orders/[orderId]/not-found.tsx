import { PackageIcon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { buttonVariants } from "@/components/ui/button-variants";

export default function SalesOrderNotFound(): React.JSX.Element {
  return (
    <EmptyState
      icon={PackageIcon}
      title="Sales order not found"
      description="It may have been a draft that was deleted, or it belongs to a territory outside yours."
      action={
        <Link href="/sales-orders" className={buttonVariants({ variant: "outline" })}>
          Back to all orders
        </Link>
      }
      className="rounded-xl border border-dashed border-border"
    />
  );
}
