import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { settingsSchema, type Setting, type SettingsPatchRequest } from "./settings.schemas";

const log = createLogger({ file: "features/settings/api/settings.api.ts", dataId: "ADMN-007" });

/** ADMN-007 · GET /settings — staff only. */
export function listSettings(signal?: AbortSignal): Promise<Setting[]> {
  return apiRequest({
    dataId: "ADMN-007",
    logger: log,
    fn: "listSettings",
    path: "/settings",
    schema: settingsSchema,
    signal,
  });
}

/** ADMN-007 · PATCH /settings — `masters.edit`; answers the full list, 422 on a bad value or key. */
export function patchSettings(body: SettingsPatchRequest): Promise<Setting[]> {
  return apiRequest({
    dataId: "ADMN-007",
    logger: log,
    fn: "patchSettings",
    method: "PATCH",
    path: "/settings",
    body,
    schema: settingsSchema,
  });
}
