import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  achievementSchema,
  personTargetsSchema,
  type Achievement,
  type PersonTargets,
  type SetTargetsRequest,
} from "./targets.schemas";

const log = createLogger({ file: "features/targets/api/targets.api.ts", dataId: "TGT-001" });

/** TGT-001 · GET /targets/achievement: you and everyone below you, with or without a target. */
export function getAchievement(month: string, signal?: AbortSignal): Promise<Achievement> {
  return apiRequest({
    dataId: "TGT-001",
    logger: log,
    fn: "getAchievement",
    path: "/targets/achievement",
    query: { month },
    schema: achievementSchema,
    signal,
  });
}

/** TGT-002 · GET /targets: one person's targets for the month, with who changed what. */
export function getPersonTargets(
  userId: string,
  month: string,
  signal?: AbortSignal,
): Promise<PersonTargets> {
  return apiRequest({
    dataId: "TGT-002",
    logger: log,
    fn: "getPersonTargets",
    path: "/targets",
    query: { user_id: userId, month },
    schema: personTargetsSchema,
    signal,
  });
}

/** TGT-002 · PUT /targets: the measures that change; the others keep their value. */
export function setTargets({
  body,
  idempotencyKey,
}: {
  body: SetTargetsRequest;
  idempotencyKey: string;
}): Promise<PersonTargets> {
  return apiRequest({
    dataId: "TGT-002",
    logger: log,
    fn: "setTargets",
    method: "PUT",
    path: "/targets",
    body,
    idempotencyKey,
    schema: personTargetsSchema,
  });
}
