import { Location01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { PageContainer } from "@/components/patterns/page-container";
import { buttonVariants } from "@/components/ui/button-variants";

export default function AppNotFound(): React.JSX.Element {
  return (
    <PageContainer className="min-h-full justify-center">
      <EmptyState
        icon={Location01Icon}
        title="Page not found"
        description="It may have been removed, or the link is wrong."
        action={
          <Link href="/dashboard" className={buttonVariants({ variant: "outline" })}>
            Back to the dashboard
          </Link>
        }
      />
    </PageContainer>
  );
}
