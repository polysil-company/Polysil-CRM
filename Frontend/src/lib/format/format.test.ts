import { describe, expect, it } from "vitest";

import {
  EMPTY_VALUE,
  formatCount,
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
  sumRupees,
  toRupeeNumber,
  todayInIndia,
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

  it("formats money the API sends as decimal strings, and refuses anything else", () => {
    expect(formatInr("125000.00")).toBe("₹1,25,000");
    expect(formatInr("1234.5", { paise: true })).toBe("₹1,234.50");
    expect(formatInrCompact("4500000.00")).toBe("₹45 L");
    expect(formatInr("1E+5")).toBe(EMPTY_VALUE);
    expect(formatInr("₹1,25,000")).toBe(EMPTY_VALUE);
    expect(formatInrCompact("")).toBe(EMPTY_VALUE);
  });

  it("marks a count that stopped at a ceiling", () => {
    expect(formatCount(74)).toBe("74");
    expect(formatCount(1000, { atLeast: true })).toBe("1,000+");
  });
});

describe("[LEAD-001] exact rupee totals", () => {
  it("adds decimal strings in whole paise, without floating-point dust", () => {
    expect(sumRupees(["0.10", "0.20"])).toBe("0.30");
    expect(sumRupees(["125000.50", null, "99.5", undefined])).toBe("125100.00");
    expect(sumRupees(["9999999999.99", "0.01"])).toBe("10000000000.00");
  });

  it("rounds the third decimal half away from zero, and handles negatives", () => {
    expect(sumRupees(["10.005"])).toBe("10.01");
    expect(sumRupees(["-10.50", "5"])).toBe("-5.50");
    expect(sumRupees([12.5, 0.25])).toBe("12.75");
  });

  it("counts unreadable amounts as zero instead of failing the whole total", () => {
    expect(sumRupees(["100", "not money", "1E+5"])).toBe("100.00");
    expect(sumRupees([])).toBe("0.00");
  });

  it("reads plain decimals for display only", () => {
    expect(toRupeeNumber(" 42.5 ")).toBe(42.5);
    expect(toRupeeNumber(7)).toBe(7);
    expect(toRupeeNumber("1,000")).toBeNull();
    expect(toRupeeNumber(null)).toBeNull();
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

  it("gives today's date in India, already tomorrow there late in the UTC evening", () => {
    expect(todayInIndia(NOW)).toBe("2026-09-14");
    expect(todayInIndia(new Date("2026-09-14T19:00:00Z"))).toBe("2026-09-15");
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
