import { queryOptions } from "@tanstack/react-query";

import { listSettings } from "./settings.api";

export const settingKeys = {
  all: ["settings"] as const,
};

/** ADMN-007 · The company's settings. */
export function settingsQueryOptions() {
  return queryOptions({
    queryKey: settingKeys.all,
    queryFn: ({ signal }) => listSettings(signal),
    meta: { dataId: "ADMN-007" },
  });
}
