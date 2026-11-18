import type { HolidayWire } from "@/features/masters/api/holidays.schemas";

/** Sample holidays for the mock; the client keeps the real list in the app. */
export function seedHolidays(): HolidayWire[] {
  return [
    { day: "2026-01-26", name: "Republic Day" },
    { day: "2026-08-15", name: "Independence Day" },
    { day: "2026-10-02", name: "Gandhi Jayanti" },
    { day: "2026-11-09", name: "Diwali" },
    { day: "2026-11-10", name: "New Year (Gujarati)" },
    { day: "2026-12-25", name: "Christmas" },
    { day: "2027-01-26", name: "Republic Day" },
  ];
}
