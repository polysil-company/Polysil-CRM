import type { Route } from "next";

/**
 * Where signed-in and signed-out visitors belong (AUTH-006). Pure functions,
 * shared by proxy.ts, the sign-in page and the session gate.
 */

export const SIGN_IN_PATH = "/sign-in";
export const HOME_PATH = "/dashboard";

/** Paths a signed-out visitor may open. Every other page needs a session. */
const PUBLIC_PATHS: readonly string[] = [SIGN_IN_PATH];

/**
 * Pages anyone may open, signed in or not, and never redirected: the link a customer gets
 * with their quotation (QUOT-012), and the enquiry page a printed QR code opens (LEAD-014).
 * They call only the backend's `/public` endpoints.
 */
const OPEN_PATH_PREFIXES: readonly string[] = ["/q/"];
const OPEN_PATHS: readonly string[] = ["/enquiry"];

export function isOpenPath(pathname: string): boolean {
  return (
    OPEN_PATHS.includes(pathname) ||
    OPEN_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}

/**
 * - `password-changed`: the user changed their own password, which signs out every session
 *   (AUTH-007);
 * - `password-reset`: an administrator set a new password while the user was changing theirs.
 */
export const SESSION_END_REASONS = [
  "signed-out",
  "session-ended",
  "password-changed",
  "password-reset",
] as const;

export type SessionEndReason = (typeof SESSION_END_REASONS)[number];

export function isSessionEndReason(value: unknown): value is SessionEndReason {
  return SESSION_END_REASONS.some((reason) => reason === value);
}

/**
 * Typed routes cannot know a return path at compile time. Every path that reaches
 * this guard has already been checked to be a same-site path.
 */
function isRoute(path: string): path is Route {
  return path.startsWith("/");
}

const MAX_NEXT_PATH_LENGTH = 512;

/**
 * A same-site path to return to after sign-in, or null.
 *
 * Refuses anything that could send the visitor to another site: absolute URLs,
 * protocol-relative `//host`, backslashes (which browsers treat as slashes) and
 * control characters. Never returns the sign-in page itself.
 */
export function safeNextPath(value: string | null | undefined): Route | null {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_NEXT_PATH_LENGTH) {
    return null;
  }
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return null;
  }
  if ([...value].some((character) => character.charCodeAt(0) < 32)) {
    return null;
  }
  const pathname = value.split(/[?#]/, 1)[0] ?? "";
  if (pathname === SIGN_IN_PATH || pathname.startsWith(`${SIGN_IN_PATH}/`)) {
    return null;
  }
  return isRoute(value) ? value : null;
}

export interface SignInPathOptions {
  /** Where to go after signing in. Dropped unless it is a safe same-site path. */
  readonly next?: string | null;
  readonly reason?: SessionEndReason | null;
}

/** `/sign-in?next=%2Fleads&reason=session-ended` */
export function signInPath({ next, reason }: SignInPathOptions = {}): Route {
  const params = new URLSearchParams();
  const safeNext = safeNextPath(next);
  if (safeNext !== null && safeNext !== "/" && safeNext !== HOME_PATH) {
    params.set("next", safeNext);
  }
  if (reason) {
    params.set("reason", reason);
  }
  const query = params.toString();
  const path = query === "" ? SIGN_IN_PATH : `${SIGN_IN_PATH}?${query}`;
  return isRoute(path) ? path : "/sign-in";
}

export interface AuthRedirectInput {
  readonly pathname: string;
  /** The query string including its leading "?", or "". */
  readonly search: string;
  readonly hasSession: boolean;
}

/**
 * For proxy.ts: where to send this page request, or null to let it through.
 * An optimistic check for a fast redirect, not security.
 */
export function decideAuthRedirect({
  pathname,
  search,
  hasSession,
}: AuthRedirectInput): string | null {
  if (isOpenPath(pathname)) {
    return null;
  }
  if (!hasSession && !PUBLIC_PATHS.includes(pathname)) {
    return signInPath({ next: `${pathname}${search}` });
  }
  if (hasSession && pathname === SIGN_IN_PATH) {
    return safeNextPath(new URLSearchParams(search).get("next")) ?? HOME_PATH;
  }
  return null;
}
