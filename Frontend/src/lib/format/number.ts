/** Shown wherever a value is missing. One glyph everywhere — never "N/A", "-" or "null". */
export const EMPTY_VALUE = "—";

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

const integerFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** 1234567 → "12,34,567" (Indian digit grouping). */
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (!isFiniteNumber(value)) {
    return EMPTY_VALUE;
  }
  if (decimals === 0) {
    return integerFormat.format(value);
  }
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** 42 → "42%". Input is a percentage (0–100), not a ratio. */
export function formatPercent(value: number | null | undefined, decimals = 0): string {
  if (!isFiniteNumber(value)) {
    return EMPTY_VALUE;
  }
  return `${formatNumber(value, decimals)}%`;
}

/** 12.5 → "+12.5%", -3 → "−3.0%" (true minus sign, U+2212). */
export function formatDelta(value: number | null | undefined, decimals = 1): string {
  if (!isFiniteNumber(value)) {
    return EMPTY_VALUE;
  }
  const magnitude = formatNumber(Math.abs(value), decimals);
  if (value > 0) return `+${magnitude}%`;
  if (value < 0) return `−${magnitude}%`;
  return `${magnitude}%`;
}

export function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}
