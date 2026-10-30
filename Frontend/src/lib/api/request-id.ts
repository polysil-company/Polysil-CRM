/**
 * Creates a UUID v4 request ID, sent as `x-request-id` so one request can be
 * found in both frontend and backend logs.
 *
 * `crypto.randomUUID` only exists in secure contexts (HTTPS or localhost).
 * Testing on a phone over the LAN (http://192.168.x.x) is not secure, so fall
 * back to `crypto.getRandomValues`, which works everywhere.
 */
export function createRequestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  // Per RFC 9562 §5.4: set version (4) and variant (10xx) bits.
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
