import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { dutySchema, type Duty, type DutyEndRequest, type DutyStartRequest } from "./duty.schemas";

const log = createLogger({ file: "features/tracking/api/duty.api.ts", dataId: "TRK-008" });

/** TRK-008 · Go on duty. 201 new, 200 the session already open; 409 `consent_required`. */
export function startDuty({
  body,
  idempotencyKey,
}: {
  readonly body: DutyStartRequest;
  readonly idempotencyKey: string;
}): Promise<Duty> {
  return apiRequest({
    dataId: "TRK-008",
    logger: log,
    fn: "startDuty",
    method: "POST",
    path: "/tracking/duty/start",
    body,
    idempotencyKey,
    schema: dutySchema,
  });
}

/** TRK-008 · Go off duty. 404 `duty_not_found` for an id that isn't yours. */
export function endDuty({
  body,
  idempotencyKey,
}: {
  readonly body: DutyEndRequest;
  readonly idempotencyKey: string;
}): Promise<Duty> {
  return apiRequest({
    dataId: "TRK-008",
    logger: log,
    fn: "endDuty",
    method: "POST",
    path: "/tracking/duty/end",
    body,
    idempotencyKey,
    schema: dutySchema,
  });
}
