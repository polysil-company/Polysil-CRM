/**
 * Makes values safe to log: strips secrets and personal data, bounds size,
 * and survives circular references. Every payload goes through `redact`
 * before it reaches a transport — callers never need to remember to do it.
 *
 * Matching is by normalised key name ("Bank_Account-No" → "bankaccountno").
 * Extend the sets below when the backend contract introduces new sensitive
 * fields, and add a test case in `redact.test.ts`.
 */

export const REDACTED = "[REDACTED]";

const MAX_DEPTH = 6;
const MAX_STRING_LENGTH = 500;
const MAX_ARRAY_ITEMS = 25;
const MAX_OBJECT_KEYS = 50;
const MAX_STACK_LENGTH = 1200;

/** Keys that are always fully redacted. */
const SECRET_KEYS = new Set([
  "password",
  "passcode",
  "otp",
  "pin",
  "mpin",
  "secret",
  "authorization",
  "cookie",
  "setcookie",
  "apikey",
  "xapikey",
  "aadhaar",
  "aadhar",
  "aadhaarnumber",
  "pan",
  "panno",
  "pannumber",
  "accountno",
  "accountnumber",
  "bankaccount",
  "bankaccountnumber",
  "ifsc",
  "ifsccode",
  "cvv",
  "cardnumber",
  "upi",
  "upiid",
  "signature",
]);

/** Any key ending in one of these is fully redacted (e.g. accessToken, webhookSecret). */
const SECRET_SUFFIXES = ["token", "secret", "password", "apikey"];

/** String values under these keys keep only their last 4 digits. */
const PHONE_SUFFIXES = [
  "phone",
  "mobile",
  "whatsapp",
  "phonenumber",
  "mobilenumber",
  "contactnumber",
];

/** String values under these keys are masked to the first character and the domain. */
const EMAIL_SUFFIXES = ["email", "emailaddress"];

function normalizeKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function endsWithAny(value: string, suffixes: readonly string[]): boolean {
  return suffixes.some((suffix) => value.endsWith(suffix));
}

/** "+91 98123 45678" → "******5678" */
export function maskPhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  return digits.length < 4 ? "****" : `******${digits.slice(-4)}`;
}

/** "ramesh.patel@example.com" → "r***@example.com" */
export function maskEmail(value: string): string {
  const [local, domain] = value.split("@");
  if (!local || !domain) {
    return REDACTED;
  }
  return `${local.slice(0, 1)}***@${domain}`;
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}…[+${value.length - max} chars]` : value;
}

/** Returns a log-safe copy of `value`. Never throws. */
export function redact(value: unknown): unknown {
  try {
    return redactValue(value, 0, []);
  } catch {
    return "[Unserializable]";
  }
}

function redactValue(value: unknown, depth: number, ancestors: object[]): unknown {
  if (value === null || value === undefined) {
    return value;
  }

  switch (typeof value) {
    case "string":
      return truncate(value, MAX_STRING_LENGTH);
    case "number":
    case "boolean":
      return value;
    case "bigint":
      return value.toString();
    case "function":
      return "[Function]";
    case "symbol":
      return value.toString();
    case "object":
      return redactObject(value, depth, ancestors);
    default:
      return String(value);
  }
}

function redactObject(value: object, depth: number, ancestors: object[]): unknown {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? "[Invalid Date]" : value.toISOString();
  }
  if (value instanceof Error) {
    return serializeError(value, depth, ancestors);
  }
  if (typeof Headers !== "undefined" && value instanceof Headers) {
    return redactValue(Object.fromEntries(value.entries()), depth, ancestors);
  }
  if (typeof URLSearchParams !== "undefined" && value instanceof URLSearchParams) {
    return redactValue(Object.fromEntries(value.entries()), depth, ancestors);
  }
  if (typeof FormData !== "undefined" && value instanceof FormData) {
    return { "[FormData keys]": [...new Set(value.keys())] };
  }
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return `[Blob ${value.type || "unknown"} ${value.size} bytes]`;
  }
  if (depth >= MAX_DEPTH) {
    return "[MaxDepth]";
  }
  if (ancestors.includes(value)) {
    return "[Circular]";
  }

  ancestors.push(value);
  try {
    if (Array.isArray(value)) {
      const items: unknown[] = value
        .slice(0, MAX_ARRAY_ITEMS)
        .map((item: unknown) => redactValue(item, depth + 1, ancestors));
      if (value.length > MAX_ARRAY_ITEMS) {
        items.push(`[+${value.length - MAX_ARRAY_ITEMS} more items]`);
      }
      return items;
    }

    const entries = Object.entries(value);
    const output: Record<string, unknown> = {};
    for (const [key, entryValue] of entries.slice(0, MAX_OBJECT_KEYS)) {
      output[key] = redactEntry(key, entryValue, depth, ancestors);
    }
    if (entries.length > MAX_OBJECT_KEYS) {
      output["[truncated]"] = `+${entries.length - MAX_OBJECT_KEYS} keys`;
    }
    return output;
  } finally {
    ancestors.pop();
  }
}

function redactEntry(key: string, value: unknown, depth: number, ancestors: object[]): unknown {
  const normalized = normalizeKey(key);

  if (SECRET_KEYS.has(normalized) || endsWithAny(normalized, SECRET_SUFFIXES)) {
    return value === null || value === undefined ? value : REDACTED;
  }
  if (typeof value === "string" && endsWithAny(normalized, PHONE_SUFFIXES)) {
    return maskPhone(value);
  }
  if (typeof value === "string" && endsWithAny(normalized, EMAIL_SUFFIXES)) {
    return maskEmail(value);
  }
  return redactValue(value, depth + 1, ancestors);
}

function serializeError(error: Error, depth: number, ancestors: object[]): Record<string, unknown> {
  const own: Record<string, unknown> = {};
  for (const [key, entryValue] of Object.entries(error)) {
    own[key] = redactEntry(key, entryValue, depth, ancestors);
  }

  return {
    name: error.name,
    message: truncate(error.message, MAX_STRING_LENGTH),
    ...own,
    ...(error.stack === undefined ? {} : { stack: truncate(error.stack, MAX_STACK_LENGTH) }),
    ...(error.cause === undefined ? {} : { cause: redactValue(error.cause, depth + 1, ancestors) }),
  };
}
