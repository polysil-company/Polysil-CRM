"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type * as React from "react";

import { Spinner } from "@/components/ui/spinner";
import { useSession } from "@/features/session/hooks/use-session";

/**
 * FARM-001 · A farmer's session works only in the portal: every other route answers 403
 * `consumer_not_allowed`. So a farmer who lands in the main app (after sign-in, or from an old
 * link) goes straight to `/portal` instead of seeing a screen of refusals.
 */
export function FarmersToPortal({ children }: { children: React.ReactNode }): React.JSX.Element {
  const session = useSession();
  const router = useRouter();
  const consumer = session.data?.userType === "consumer";

  useEffect(() => {
    if (consumer) router.replace("/portal");
  }, [consumer, router]);

  if (consumer) {
    return (
      <main
        aria-label="Opening your record"
        className="flex min-h-dvh items-center justify-center bg-background"
      >
        <Spinner />
      </main>
    );
  }
  return <>{children}</>;
}
