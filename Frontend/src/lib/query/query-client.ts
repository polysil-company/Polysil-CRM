import { isServer, MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { isApiError } from "@/lib/api/errors";
import type { DataId } from "@/lib/data-ids";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "lib/query/query-client.ts", dataId: "OBS-002" });

declare module "@tanstack/react-query" {
  interface Register {
    /** Every query declares the functionality it belongs to (set in its queryOptions factory). */
    queryMeta: { dataId: DataId };
    mutationMeta: { dataId: DataId };
  }
}

/**
 * Cache policy defaults. Per-query overrides live in each feature's
 * queryOptions factory, next to the query — never inline in a component.
 *
 * - staleTime 30s: navigating back to a list within 30s shows cached data
 *   instantly and does not refetch.
 * - retries: only failures a retry can fix (network, timeout, 408, 429, 5xx),
 *   at most twice. A 4xx or a contract violation will not fix itself.
 */
export const QUERY_DEFAULTS = {
  staleTime: 30_000,
  gcTime: 5 * 60_000,
  maxRetries: 2,
} as const;

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= QUERY_DEFAULTS.maxRetries) {
    return false;
  }
  return isApiError(error) && error.isRetryable;
}

export function retryDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 8000);
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        const fields = {
          ...(query.meta === undefined ? {} : { dataId: query.meta.dataId }),
          context: { queryKey: query.queryKey, failures: query.state.fetchFailureCount },
          error,
        };
        // ApiErrors were already logged in detail by apiRequest; anything else is unexpected.
        if (isApiError(error)) {
          log.debug("queryCache.onError", "query settled with an error", fields);
        } else {
          log.error("queryCache.onError", "query failed with a non-API error", fields);
        }
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _onMutateResult, mutation) => {
        const fields = {
          ...(mutation.meta === undefined ? {} : { dataId: mutation.meta.dataId }),
          context: { mutationKey: mutation.options.mutationKey },
          error,
        };
        if (isApiError(error)) {
          log.debug("mutationCache.onError", "mutation settled with an error", fields);
        } else {
          log.error("mutationCache.onError", "mutation failed with a non-API error", fields);
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: QUERY_DEFAULTS.staleTime,
        gcTime: QUERY_DEFAULTS.gcTime,
        retry: shouldRetry,
        retryDelay,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

/**
 * Server: a fresh client per request (never share cache between users).
 * Browser: one client for the page lifetime.
 */
export function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}
