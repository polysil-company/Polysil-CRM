"use client";

import { parseAsString, useQueryState } from "nuqs";

import { todayInIndia } from "@/lib/format";

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** Whether text is a calendar day like 2026-10-18. */
export function isCalendarDay(value: string): boolean {
  return DAY_PATTERN.test(value);
}

/**
 * TRK-002, TRK-005 · An Indian calendar day in the URL (`?date=`), so a day can be sent to a
 * colleague; today by default, never later than today.
 */
export function useDayParam(): [string, (day: string) => void] {
  const today = todayInIndia();
  const [value, setValue] = useQueryState("date", parseAsString);
  const day = value !== null && isCalendarDay(value) && value <= today ? value : today;
  return [
    day,
    (next) => {
      void setValue(next === today ? null : next);
    },
  ];
}
