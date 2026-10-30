"use client";

import { useEffect } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { PageContainer } from "@/components/patterns/page-container";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "app/(app)/error.tsx", dataId: "APP-003" });

/** Route-level boundary for rendering errors inside the app shell. The shell stays usable. */
export default function AppError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}): React.JSX.Element {
  useEffect(() => {
    log.error("AppError", "page failed to render", { error, context: { digest: error.digest } });
  }, [error]);

  return (
    <PageContainer className="min-h-full justify-center">
      <ErrorState error={error} onRetry={retry} />
    </PageContainer>
  );
}
