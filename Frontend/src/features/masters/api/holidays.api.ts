import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  holidaySchema,
  holidaysSchema,
  type AddHolidayRequest,
  type Holiday,
} from "./holidays.schemas";

const log = createLogger({ file: "features/masters/api/holidays.api.ts", dataId: "MSTR-019" });

/** MSTR-019 · A year's holidays (any signed-in user). */
export function listHolidays(year: number, signal?: AbortSignal): Promise<Holiday[]> {
  return apiRequest({
    dataId: "MSTR-019",
    logger: log,
    fn: "listHolidays",
    path: "/holidays",
    query: { year },
    schema: holidaysSchema,
    signal,
  });
}

/**
 * MSTR-019 · Add a holiday (masters.edit). 409 `holiday_exists`; 422 `holiday_in_past` (today or
 * earlier, IST) or `holiday_sunday`.
 */
export function addHoliday({
  body,
  idempotencyKey,
}: {
  readonly body: AddHolidayRequest;
  readonly idempotencyKey: string;
}): Promise<Holiday> {
  return apiRequest({
    dataId: "MSTR-019",
    logger: log,
    fn: "addHoliday",
    method: "POST",
    path: "/holidays",
    body,
    idempotencyKey,
    schema: holidaySchema,
  });
}

/** MSTR-019 · Remove a future holiday (masters.edit). 409 `holiday_in_past`. */
export function removeHoliday({
  day,
  idempotencyKey,
}: {
  readonly day: string;
  readonly idempotencyKey: string;
}): Promise<void> {
  return apiRequest({
    dataId: "MSTR-019",
    logger: log,
    fn: "removeHoliday",
    method: "DELETE",
    path: `/holidays/${encodeURIComponent(day)}`,
    idempotencyKey,
    schema: z.undefined(),
  });
}
