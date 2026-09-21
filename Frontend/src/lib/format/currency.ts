import { EMPTY_VALUE, formatNumber, isFiniteNumber, roundTo } from "./number";

// TODO(LEAD-001): confirm the money unit with the backend (rupees as decimal vs integer paise).
// Formatters take RUPEES. If the API sends paise, convert once in the feature's schema transform.

const CRORE = 10_000_000;
const LAKH = 100_000;

const inrWhole = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inrPaise = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** 123456 → "₹1,23,456"; with `paise: true` → "₹1,23,456.00". */
export function formatInr(
  amount: number | null | undefined,
  options: { paise?: boolean } = {},
): string {
  if (!isFiniteNumber(amount)) {
    return EMPTY_VALUE;
  }
  return (options.paise ? inrPaise : inrWhole).format(amount);
}

/**
 * Compact rupees in lakh and crore, formatted identically in every browser:
 * 4_50_00_000 → "₹4.5 Cr", 1_25_000 → "₹1.25 L", 45_500 → "₹45,500".
 */
export function formatInrCompact(amount: number | null | undefined): string {
  if (!isFiniteNumber(amount)) {
    return EMPTY_VALUE;
  }

  const sign = amount < 0 ? "−" : "";
  const absolute = Math.abs(amount);
  const crores = roundTo(absolute / CRORE, 2);
  const lakhs = roundTo(absolute / LAKH, 2);

  if (crores >= 1) {
    return `${sign}₹${trimZeros(crores)} Cr`;
  }
  // 99.999 lakh rounds to 100 L — promote it to 1 Cr instead.
  if (lakhs >= 100) {
    return `${sign}₹1 Cr`;
  }
  if (lakhs >= 1) {
    return `${sign}₹${trimZeros(lakhs)} L`;
  }
  return `${sign}₹${formatNumber(Math.round(absolute))}`;
}

function trimZeros(value: number): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}
