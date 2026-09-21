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

const relative = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });

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
