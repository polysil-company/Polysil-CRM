import { z } from "zod";

/**
 * MSTR-019 · Holidays (FS-028, `complaint-holidays-escalation.md`): complaint targets count
 * working hours, Monday to Saturday, 09:30 to 18:30 IST, and a holiday counts like a Sunday.
 */

const holidayWireSchema = z.object({
  day: z.iso.date(),
  name: z.string(),
});

export type HolidayWire = z.input<typeof holidayWireSchema>;

export interface Holiday {
  readonly day: string;
  readonly name: string;
}

/** `GET /holidays?year=` — the year's holidays, by day. */
export const holidaysSchema = z
  .object({ data: z.array(holidayWireSchema) })
  .transform(({ data }): Holiday[] => [...data].sort((a, b) => a.day.localeCompare(b.day)));

/** `POST /holidays` answers the holiday. */
export const holidaySchema = z
  .object({ data: holidayWireSchema })
  .transform(({ data }): Holiday => data);

export interface AddHolidayRequest {
  readonly day: string;
  readonly name: string;
}

export const HOLIDAY_NAME_MAX_LENGTH = 100;
