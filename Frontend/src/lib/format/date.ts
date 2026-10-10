import { EMPTY_VALUE } from "./number";

/**
 * All dates render in India Standard Time regardless of the device clock, so
 * a follow-up "today" means the same day for everyone. The API sends ISO 8601
 * timestamps with an offset; never parse locale strings.
 */
export const APP_TIME_ZONE = "Asia/Kolkata";

const dayMonth = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIME_ZONE,
  day: "numeric",
  month: "short",
});

const dayMonthYear = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIME_ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});

const dateTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIME_ZONE,
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const timeOnly = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const yearOnly = new Intl.DateTimeFormat("en-IN", { timeZone: APP_TIME_ZONE, year: "numeric" });

/** en-CA writes dates as YYYY-MM-DD, the API's calendar-date format. */
const isoDay = new Intl.DateTimeFormat("en-CA", {
  timeZone: APP_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const relative = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });

/** 24-hour "HH:MM", the value an `<input type="time">` holds. */
const clock24 = new Intl.DateTimeFormat("en-GB", {
  timeZone: APP_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const weekdayDayMonth = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
});

export type DateInput = string | Date | null | undefined;

/** Returns a valid Date or null. Never throws. */
export function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "14 Sept" in the current year, "14 Sept 2025" otherwise. */
export function formatDate(value: DateInput, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) {
    return EMPTY_VALUE;
  }
  const sameYear = yearOnly.format(date) === yearOnly.format(now);
  return (sameYear ? dayMonth : dayMonthYear).format(date);
}

/** "14 Sept 2026" — always with the year. */
export function formatFullDate(value: DateInput): string {
  const date = toDate(value);
  return date ? dayMonthYear.format(date) : EMPTY_VALUE;
}

/** "14 Sept, 4:05 pm" */
export function formatDateTime(value: DateInput): string {
  const date = toDate(value);
  return date ? dateTime.format(date) : EMPTY_VALUE;
}

/** "4:05 pm" */
export function formatTime(value: DateInput): string {
  const date = toDate(value);
  return date ? timeOnly.format(date) : EMPTY_VALUE;
}

/**
 * Today's calendar date in India as "YYYY-MM-DD" — the form the API uses for dates such as a
 * quotation's `valid_until`, so the two compare as strings.
 */
export function todayInIndia(now: Date = new Date()): string {
  return isoDay.format(now);
}

/** The calendar day in India of an instant, "YYYY-MM-DD" — for an `<input type="date">`. */
export function calendarDayOf(value: DateInput): string {
  const date = toDate(value);
  return date ? isoDay.format(date) : "";
}

/** The time of day in India of an instant, 24-hour "HH:MM" — for an `<input type="time">`. */
export function timeOfDayOf(value: DateInput): string {
  const date = toDate(value);
  return date ? clock24.format(date) : "";
}

/** A calendar day ("YYYY-MM-DD") moved by a number of days: 2026-10-31 + 1 → 2026-11-01. */
export function shiftCalendarDay(day: string, days: number): string {
  const noon = Date.parse(`${day}T12:00:00Z`);
  return new Date(noon + days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/** A calendar day ("YYYY-MM-DD") as a heading: "Friday, 3 October". */
export function formatCalendarDay(day: string): string {
  // Midday in India keeps the day the same whatever the browser's own time zone.
  const date = toDate(`${day}T12:00:00+05:30`);
  return date ? weekdayDayMonth.format(date) : EMPTY_VALUE;
}

/** True when both fall on the same calendar day in India. */
export function isSameDay(a: DateInput, b: DateInput): boolean {
  const first = toDate(a);
  const second = toDate(b);
  return (
    first !== null && second !== null && dayMonthYear.format(first) === dayMonthYear.format(second)
  );
}

const UNITS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60],
  ["month", 30 * 24 * 60 * 60],
  ["week", 7 * 24 * 60 * 60],
  ["day", 24 * 60 * 60],
  ["hour", 60 * 60],
  ["minute", 60],
];

/** "in 3 days", "2 hours ago", "yesterday", "now". */
export function formatRelativeTime(value: DateInput, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) {
    return EMPTY_VALUE;
  }
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  for (const [unit, unitSeconds] of UNITS) {
    if (Math.abs(seconds) >= unitSeconds) {
      return relative.format(Math.round(seconds / unitSeconds), unit);
    }
  }
  return relative.format(0, "second");
}

/** True when the date is in the past. */
export function isPast(value: DateInput, now: Date = new Date()): boolean {
  const date = toDate(value);
  return date !== null && date.getTime() < now.getTime();
}
