import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { sessionSchema, type Session } from "./session.schemas";

const log = createLogger({ file: "features/session/api/session.api.ts", dataId: "AUTH-002" });

export function fetchSession(signal?: AbortSignal): Promise<Session> {
  return apiRequest({
    dataId: "AUTH-002",
    logger: log,
    fn: "fetchSession",
    path: "/me",
    schema: sessionSchema,
    signal,
  });
}
