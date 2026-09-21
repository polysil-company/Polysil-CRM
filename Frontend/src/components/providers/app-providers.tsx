"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { MotionConfig } from "motion/react";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useEffect } from "react";
import type * as React from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { clientEnv } from "@/lib/env/client";
import { installLoggerDevtools } from "@/lib/logger";
import { getQueryClient } from "@/lib/query/query-client";

import { MockGate } from "./mock-gate";

/**
 * Every client-side provider, in one place:
 * TanStack Query (server state) · nuqs (URL state) · Motion (respects reduced
 * motion) · tooltips · toasts · the mock backend gate.
 */
export function AppProviders({ children }: { children: React.ReactNode }): React.JSX.Element {
  const queryClient = getQueryClient();

  useEffect(() => {
    installLoggerDevtools();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <NuqsAdapter>
        <MotionConfig reducedMotion="user">
          <TooltipProvider>
            <MockGate>{children}</MockGate>
            <Toaster />
          </TooltipProvider>
        </MotionConfig>
      </NuqsAdapter>
      {clientEnv.appEnv === "development" ? (
        <ReactQueryDevtools buttonPosition="bottom-left" />
      ) : null}
    </QueryClientProvider>
  );
}
