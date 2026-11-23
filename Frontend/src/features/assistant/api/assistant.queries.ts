import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { listAssistantActions, searchAssistant } from "./assistant.api";

export const assistantKeys = {
  all: ["assistant"] as const,
  search: (q: string) => [...assistantKeys.all, "search", q] as const,
  actions: () => [...assistantKeys.all, "actions"] as const,
};

/**
 * BOT-001 · The answer for what was typed. A new term leaves the old request without a
 * listener, so TanStack Query cancels it; the last answer stays on screen meanwhile.
 */
export function assistantSearchQueryOptions(q: string) {
  return queryOptions({
    queryKey: assistantKeys.search(q),
    queryFn: ({ signal }) => searchAssistant(q, signal),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    meta: { dataId: "BOT-001" },
  });
}

/** BOT-002 · Everything the user may do. */
export function assistantActionsQueryOptions() {
  return queryOptions({
    queryKey: assistantKeys.actions(),
    queryFn: ({ signal }) => listAssistantActions(signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "BOT-002" },
  });
}
