import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import type * as React from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

/** A fresh client per test: no retries (errors show immediately), no cache sharing between tests. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false },
    },
  });
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  queryClient?: QueryClient;
  /** Initial URL search params, e.g. "?status=won". */
  searchParams?: string;
}

/** Renders with the app's providers: TanStack Query, nuqs (in-memory URL) and tooltips. */
export function renderWithProviders(
  ui: React.ReactElement,
  {
    queryClient = createTestQueryClient(),
    searchParams = "",
    ...options
  }: RenderWithProvidersOptions = {},
): RenderResult & { queryClient: QueryClient } {
  function Wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <NuqsTestingAdapter searchParams={searchParams}>
          <TooltipProvider>{children}</TooltipProvider>
        </NuqsTestingAdapter>
      </QueryClientProvider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper, ...options }), queryClient };
}
