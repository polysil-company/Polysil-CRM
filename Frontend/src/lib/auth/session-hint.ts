/**
 * A readable "this browser has signed in" marker for proxy.ts (AUTH-006).
 *
 * The real credential is the backend's httpOnly refresh cookie. It is scoped to
 * /api/v1/auth, so page requests never carry it and proxy.ts cannot see it. This
 * marker holds no secret: it only lets proxy.ts send signed-out visitors to the
 * sign-in page before a protected screen renders. The backend still rejects
 * every request that lacks a valid access token.
 */

export const SESSION_HINT_COOKIE = "polysil_session";

/** The backend's refresh token lifetime: 30 days. */
const HINT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

function attributes(maxAgeSeconds: number): string {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  return `Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax${secure}`;
}

export function writeSessionHint(): void {
  if (typeof document === "undefined") {
    return;
  }
  document.cookie = `${SESSION_HINT_COOKIE}=1; ${attributes(HINT_MAX_AGE_SECONDS)}`;
}

export function clearSessionHint(): void {
  if (typeof document === "undefined") {
    return;
  }
  document.cookie = `${SESSION_HINT_COOKIE}=; ${attributes(0)}`;
}

export function hasSessionHint(): boolean {
  if (typeof document === "undefined") {
    return false;
  }
  return document.cookie.split(";").some((part) => part.trim() === `${SESSION_HINT_COOKIE}=1`);
}
