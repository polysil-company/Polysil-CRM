import { Location01Icon } from "@hugeicons/core-free-icons";
import type { Metadata } from "next";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { buttonVariants } from "@/components/ui/button-variants";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound(): React.JSX.Element {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <EmptyState
        icon={Location01Icon}
        title="Page not found"
        description="The link may be broken, or the page may have moved."
        action={
          <Link href="/dashboard" className={buttonVariants()}>
            Go to the dashboard
          </Link>
        }
      />
    </main>
  );
}
