import { EMPTY_VALUE, formatNumber, roundTo } from "./number";

/**
 * A rupee amount. The backend sends money as a decimal string ("125000.00") so no
 * precision is lost on the way; the formatters also accept plain numbers.
 */
type RupeeAmount = number | string;

const CRORE = 10_000_000;
const LAKH = 100_000;

/** A plain decimal: optional sign, digits, optional fraction. No exponent, no grouping. */
const DECIMAL_PATTERN = /^([+-])?(\d+)(?:\.(\d+))?$/;

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

/**
 * "125000.50" → 125000.5, 42 → 42. Anything that is not a plain decimal becomes null,
 * so a malformed value renders as "—" instead of "₹NaN". For display only: add amounts
 * with `sumRupees`, which never goes through floating point.
 */
export function toRupeeNumber(amount: RupeeAmount | null | undefined): number | null {
  if (typeof amount === "number") {
    return Number.isFinite(amount) ? amount : null;
  }
  if (typeof amount === "string" && DECIMAL_PATTERN.test(amount.trim())) {
    return Number(amount.trim());
  }
  return null;
}

/** 123456 → "₹1,23,456"; with `paise: true` → "₹1,23,456.00". Accepts decimal strings. */
export function formatInr(
  amount: RupeeAmount | null | undefined,
  options: { paise?: boolean } = {},
): string {
  const value = toRupeeNumber(amount);
  if (value === null) {
    return EMPTY_VALUE;
  }
  return (options.paise ? inrPaise : inrWhole).format(value);
}

/**
 * Compact rupees in lakh and crore, formatted identically in every browser:
 * 4_50_00_000 → "₹4.5 Cr", 1_25_000 → "₹1.25 L", 45_500 → "₹45,500". Accepts decimal strings.
 */
export function formatInrCompact(amount: RupeeAmount | null | undefined): string {
  const value = toRupeeNumber(amount);
  if (value === null) {
    return EMPTY_VALUE;
  }

  const sign = value < 0 ? "−" : "";
  const absolute = Math.abs(value);
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

/**
 * Adds rupee amounts exactly, in whole paise, and returns a decimal string:
 * ["125000.50", null, "99.5"] → "125100.00". Missing or unreadable amounts count as
 * zero, so one bad value never hides the rest of a total.
 */
export function sumRupees(amounts: readonly (RupeeAmount | null | undefined)[]): string {
  let paise = 0n;
  for (const amount of amounts) {
    paise += toPaise(amount) ?? 0n;
  }
  return fromPaise(paise);
}

/** Rounds half away from zero to the paisa: "10.005" → 1001n. */
function toPaise(amount: RupeeAmount | null | undefined): bigint | null {
  if (typeof amount === "number") {
    return Number.isFinite(amount) ? BigInt(Math.round(amount * 100)) : null;
  }
  if (typeof amount !== "string") {
    return null;
  }
  const match = DECIMAL_PATTERN.exec(amount.trim());
  if (match === null) {
    return null;
  }
  const [, sign, whole = "0", fraction = ""] = match;
  const cents = BigInt(whole) * 100n + BigInt(fraction.slice(0, 2).padEnd(2, "0"));
  const roundUp = (fraction[2] ?? "0") >= "5" ? 1n : 0n;
  const magnitude = cents + roundUp;
  return sign === "-" ? -magnitude : magnitude;
}

function fromPaise(paise: bigint): string {
  const negative = paise < 0n;
  const magnitude = negative ? -paise : paise;
  const whole = magnitude / 100n;
  const fraction = (magnitude % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole.toString()}.${fraction}`;
}

function trimZeros(value: number): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}
