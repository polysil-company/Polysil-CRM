import { describe, expect, it } from "vitest";

import {
  EMPTY_VALUE,
  formatDate,
  formatDateTime,
  formatDelta,
  formatIndianPhone,
  formatInr,
  formatInrCompact,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  isPast,
  normalizeIndianMobile,
} from "@/lib/format";

const NOW = new Date("2026-09-14T10:00:00+05:30");
const DAY = 24 * 60 * 60 * 1000;

describe("[DS-001] number and money formatting", () => {
  it("uses Indian digit grouping", () => {
    expect(formatNumber(1_234_567)).toBe("12,34,567");
    expect(formatNumber(3.14159, 2)).toBe("3.14");
    expect(formatInr(123_456)).toBe("₹1,23,456");
    expect(formatInr(1234.5, { paise: true })).toBe("₹1,234.50");
  });

  it("compacts to lakh and crore identically everywhere", () => {
    expect(formatInrCompact(45_000_000)).toBe("₹4.5 Cr");
    expect(formatInrCompact(125_000)).toBe("₹1.25 L");
    expect(formatInrCompact(9_999_999)).toBe("₹1 Cr");
    expect(formatInrCompact(45_500)).toBe("₹45,500");
    expect(formatInrCompact(-125_000)).toBe("−₹1.25 L");
  });

  it("formats percentages and signed changes", () => {
    expect(formatPercent(42)).toBe("42%");
    expect(formatDelta(12.5)).toBe("+12.5%");
    expect(formatDelta(-3)).toBe("−3.0%");
    expect(formatDelta(0)).toBe("0.0%");
  });

  it("shows one glyph for missing values", () => {
    expect(formatNumber(null)).toBe(EMPTY_VALUE);
    expect(formatInr(Number.NaN)).toBe(EMPTY_VALUE);
    expect(formatInrCompact(undefined)).toBe(EMPTY_VALUE);
    expect(formatDelta(Number.POSITIVE_INFINITY)).toBe(EMPTY_VALUE);
  });
});

describe("[DS-001] date formatting (India Standard Time)", () => {
  it("omits the year for dates in the current year", () => {
    expect(formatDate("2026-09-14T05:00:00Z", NOW)).toMatch(/^14 Sept?$/);
    expect(formatDate("2025-09-14T05:00:00Z", NOW)).toMatch(/^14 Sept? 2025$/);
  });

  it("renders times in IST whatever the device timezone", () => {
    expect(formatDateTime("2026-09-13T19:05:00Z")).toMatch(/^14 Sept?, 12:35\s?am$/i);
  });

  it("describes relative time in words", () => {
    expect(formatRelativeTime(new Date(NOW.getTime() + 2 * DAY), NOW)).toBe("in 2 days");
    expect(formatRelativeTime(new Date(NOW.getTime() - DAY), NOW)).toBe("yesterday");
    expect(formatRelativeTime(new Date(NOW.getTime() - 3 * 60 * 60 * 1000), NOW)).toBe(
      "3 hours ago",
    );
    expect(formatRelativeTime(new Date(NOW.getTime() + 20_000), NOW)).toBe("now");
  });

  it("handles missing and invalid dates without throwing", () => {
    expect(formatDate(null, NOW)).toBe(EMPTY_VALUE);
    expect(formatDateTime("not a date")).toBe(EMPTY_VALUE);
    expect(isPast("2026-09-13T00:00:00Z", NOW)).toBe(true);
    expect(isPast(null, NOW)).toBe(false);
  });
});

describe("[DS-001] Indian mobile numbers", () => {
  it.each(["+91 98123 45678", "09812345678", "919812345678", "9812345678"])(
    "normalises %s",
    (input) => {
      expect(normalizeIndianMobile(input)).toBe("+919812345678");
    },
  );

  it("rejects numbers that are not Indian mobiles", () => {
    expect(normalizeIndianMobile("12345")).toBeNull();
    expect(normalizeIndianMobile("5812345678")).toBeNull();
  });

  it("formats for display and leaves unknown input untouched", () => {
    expect(formatIndianPhone("+919812345678")).toBe("+91 98123 45678");
    expect(formatIndianPhone("12345")).toBe("12345");
    expect(formatIndianPhone(null)).toBe(EMPTY_VALUE);
  });
});
