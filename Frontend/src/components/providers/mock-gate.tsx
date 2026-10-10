"use client";

import { useSyncExternalStore } from "react";
import type * as React from "react";

import { Spinner } from "@/components/ui/spinner";
import { clientEnv } from "@/lib/env/client";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "components/providers/mock-gate.tsx", dataId: "APP-004" });

export interface MockReadiness {
  /** The first subscriber starts the worker; every subscriber hears once it is ready. */
  subscribe: (listener: () => void) => () => void;
  isReady: () => boolean;
}

/**
 * Whether the mock service worker is running, as a tiny external store. A worker that
 * cannot start still counts as ready: the app stays usable, and requests go to the real API.
 */
export function createMockReadiness(start: () => Promise<void>): MockReadiness {
  let ready = false;
  let starting: Promise<void> | undefined;
  const listeners = new Set<() => void>();

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      starting ??= start()
        .catch((error: unknown) => {
          // Service workers need a secure origin (https or localhost).
          log.warn("startMockWorker", "mock backend could not start; requests go to the real API", {
            error,
          });
        })
        .then(() => {
          ready = true;
          for (const notify of listeners) {
            notify();
          }
        });
      return () => {
        listeners.delete(listener);
      };
    },
    isReady(): boolean {
      return ready;
    },
  };
}

const mockReadiness = createMockReadiness(async () => {
  const { worker } = await import("@/mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass", quiet: true });
  log.info("startMockWorker", "mock backend running");
});

function notReadyOnServer(): boolean {
  return false;
}

/**
 * APP-004 · When NEXT_PUBLIC_API_MOCKING is `enabled` or `partial`, shows a boot screen
 * until the mock service worker is ready, so no request escapes to the network first.
 * Does nothing in staging and production (mocking cannot be turned on there).
 *
 * The server renders the boot screen too, never the page. A server-rendered form looks
 * ready while the worker is still starting and the page is not yet hydrated, and a click
 * in that gap submits the form natively: the page reloads and the input is lost. The CI
 * smoke tests hit exactly this.
 */
export function MockGate({ children }: { children: React.ReactNode }): React.JSX.Element {
  if (clientEnv.apiMocking === "disabled") {
    return <>{children}</>;
  }
  return <WaitForMocks>{children}</WaitForMocks>;
}

function WaitForMocks({ children }: { children: React.ReactNode }): React.JSX.Element {
  const ready = useSyncExternalStore(
    mockReadiness.subscribe,
    mockReadiness.isReady,
    notReadyOnServer,
  );
  return ready ? <>{children}</> : <BootIndicator />;
}

function BootIndicator(): React.JSX.Element {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
      <Spinner label="Starting the app" className="size-5" />
    </div>
  );
}
