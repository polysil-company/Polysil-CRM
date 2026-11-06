import { EMPTY_VALUE } from "./number";

/** Indian mobile numbers: 10 digits starting 6–9. */
export const INDIAN_MOBILE_PATTERN = /^[6-9]\d{9}$/;

/**
 * Accepts "+91 98123 45678", "09812345678", "919812345678" or "9812345678".
 * Returns the canonical "+919812345678", or null when it is not a valid mobile.
 */
export function normalizeIndianMobile(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  const national =
    digits.length === 12 && digits.startsWith("91")
      ? digits.slice(2)
      : digits.length === 11 && digits.startsWith("0")
        ? digits.slice(1)
        : digits;
  return INDIAN_MOBILE_PATTERN.test(national) ? `+91${national}` : null;
}

/** "+919812345678" → "+91 98123 45678". Unrecognised input is returned unchanged. */
export function formatIndianPhone(value: string | null | undefined): string {
  if (!value) {
    return EMPTY_VALUE;
  }
  const normalized = normalizeIndianMobile(value);
  if (!normalized) {
    return value;
  }
  const national = normalized.slice(3);
  return `+91 ${national.slice(0, 5)} ${national.slice(5)}`;
}
