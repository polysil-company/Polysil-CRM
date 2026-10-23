import { Invoice03Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { buttonVariants } from "@/components/ui/button-variants";

export default function QuotationNotFound(): React.JSX.Element {
  return (
    <EmptyState
      icon={Invoice03Icon}
      title="Quotation not found"
      description="It may have been a draft that was deleted, or it belongs to a lead outside your territory."
      action={
        <Link href="/quotations" className={buttonVariants({ variant: "outline" })}>
          Back to all quotations
        </Link>
      }
      className="rounded-xl border border-dashed border-border"
    />
  );
}
