import { queryOptions } from "@tanstack/react-query";

import { getScheme, listSchemes } from "./subsidy-schemes.api";

export const schemeKeys = {
  all: ["subsidy-schemes"] as const,
  list: () => [...schemeKeys.all, "list"] as const,
  detail: (code: string, on: string | null) => [...schemeKeys.all, "detail", code, on] as const,
};

/** SUBS-014 · Every scheme. */
export function schemeListQueryOptions() {
  return queryOptions({
    queryKey: schemeKeys.list(),
    queryFn: ({ signal }) => listSchemes(signal),
    meta: { dataId: "SUBS-014" },
  });
}

/** SUBS-014 · One scheme's readiness, stages and state. */
export function schemeDetailQueryOptions(code: string, on: string | null) {
  return queryOptions({
    queryKey: schemeKeys.detail(code, on),
    queryFn: ({ signal }) => getScheme(code, on, signal),
    meta: { dataId: "SUBS-014" },
  });
}
