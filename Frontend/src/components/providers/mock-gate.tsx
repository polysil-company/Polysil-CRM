"use client";

import { Suspense, use } from "react";
import type * as React from "react";

import { Spinner } from "@/components/ui/spinner";
import { clientEnv } from "@/lib/env/client";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "components/providers/mock-gate.tsx", dataId: "APP-004" });

let workerReady: Promise<void> | undefined;

function startMockWorker(): Promise<void> {
  workerReady ??= import("@/mocks/browser")
    .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass", quiet: true }))
    .then(() => {
      log.info("startMockWorker", "mock backend running");
    })
    .catch((error: unknown) => {
      // Service workers need a secure origin (https or localhost). Keep the app usable without mocks.
      log.warn("startMockWorker", "mock backend could not start; requests go to the real API", {
        error,
      });
    });
  return workerReady;
}

function WaitForMocks({ children }: { children: React.ReactNode }): React.JSX.Element {
  if (typeof window !== "undefined") {
    use(startMockWorker());
  }
  return <>{children}</>;
}

/**
 * APP-004 · When NEXT_PUBLIC_API_MOCKING=enabled, holds rendering until the
 * mock service worker is ready, so no request escapes to the network first.
 * Does nothing in staging and production (mocking cannot be enabled there).
 */
export function MockGate({ children }: { children: React.ReactNode }): React.JSX.Element {
  if (clientEnv.apiMocking !== "enabled") {
    return <>{children}</>;
  }
  return (
    <Suspense fallback={<BootIndicator />}>
      <WaitForMocks>{children}</WaitForMocks>
    </Suspense>
  );
}

function BootIndicator(): React.JSX.Element {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
      <Spinner label="Starting the app" className="size-5" />
    </div>
  );
}
