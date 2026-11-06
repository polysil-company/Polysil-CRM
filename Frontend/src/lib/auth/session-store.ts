/**
 * The signed-in session in this tab (AUTH-004, AUTH-006).
 *
 * - The access token lives in memory only — never in localStorage and never in a
 *   readable cookie — so an injected script cannot keep it after the tab closes.
 * - The refresh token is the backend's httpOnly cookie on /api/v1/auth. This module
 *   never sees it; calling POST /auth/refresh sends it.
 * - The token is refreshed a minute before it expires, when the tab becomes visible
 *   and when the connection returns. If a request still meets an expired token,
 *   lib/api/client.ts refreshes and retries it once.
 * - Sign-out and a session that ends reach every open tab.
 */

import { apiRequest, registerAccessTokenProvider } from "@/lib/api/client";
import { isApiError, type ApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { isSessionEndReason, type SessionEndReason } from "./redirects";
import { clearSessionHint, hasSessionHint, writeSessionHint } from "./session-hint";
import { tokenResponseSchema, type SessionTokens } from "./tokens";

const log = createLogger({ file: "lib/auth/session-store.ts", dataId: "AUTH-004" });

/** Refresh this long before the access token expires. */
export const REFRESH_MARGIN_MS = 60_000;

const CHANNEL_NAME = "polysil-auth";

/**
 * - `unknown`: this tab has not looked for a session yet
 * - `checking`: exchanging the refresh cookie for an access token
 * - `signed-in`: an access token is in memory
 * - `signed-out`: no session; `endReason` says why
 * - `unreachable`: the check could not reach the backend (offline, timeout, 5xx)
 */
export type AuthStatus = "unknown" | "checking" | "signed-in" | "signed-out" | "unreachable";

export interface AuthSnapshot {
  readonly status: AuthStatus;
  /** Why the session ended. Null when the visitor never signed in on this browser. */
  readonly endReason: SessionEndReason | null;
  /** What stopped the check, while `status` is `unreachable`. */
  readonly error: ApiError | null;
}

interface SessionEndedMessage {
  readonly type: "session-ended";
  readonly reason: SessionEndReason;
}

const INITIAL_SNAPSHOT: AuthSnapshot = { status: "unknown", endReason: null, error: null };

let snapshot: AuthSnapshot = INITIAL_SNAPSHOT;
let accessToken: string | null = null;
let expiresAt = 0;
let refreshInFlight: Promise<string | null> | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let channel: BroadcastChannel | null = null;
const listeners = new Set<() => void>();

function setSnapshot(next: AuthSnapshot): void {
  if (
    next.status === snapshot.status &&
    next.endReason === snapshot.endReason &&
    next.error === snapshot.error
  ) {
    return;
  }
  snapshot = next;
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeAuth(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getAuthSnapshot(): AuthSnapshot {
  return snapshot;
}

/** The server never holds a session, so it always renders the "checking" state. */
export function getServerAuthSnapshot(): AuthSnapshot {
  return INITIAL_SNAPSHOT;
}

function hasFreshToken(): boolean {
  return accessToken !== null && Date.now() < expiresAt - REFRESH_MARGIN_MS;
}

function refreshQuietly(trigger: "scheduled" | "resume"): void {
  refreshAccessToken().catch((error: unknown) => {
    // The token stays until it expires; the next request tries again.
    log.warn("refreshQuietly", "could not refresh the session", { context: { trigger }, error });
  });
}

function scheduleRefresh(): void {
  clearTimeout(refreshTimer);
  const delayMs = Math.max(0, expiresAt - REFRESH_MARGIN_MS - Date.now());
  refreshTimer = setTimeout(() => {
    refreshQuietly("scheduled");
  }, delayMs);
}

/** Keeps the tokens from a successful sign-in or refresh. */
export function acceptSessionTokens(tokens: SessionTokens): void {
  accessToken = tokens.accessToken;
  expiresAt = Date.now() + tokens.expiresInSeconds * 1000;
  writeSessionHint();
  setSnapshot({ status: "signed-in", endReason: null, error: null });
  scheduleRefresh();
}

/** Ends the session in this tab and, unless the news came from another tab, in every open tab. */
export function endSession(
  reason: SessionEndReason,
  { fromOtherTab = false }: { fromOtherTab?: boolean } = {},
): void {
  clearTimeout(refreshTimer);
  accessToken = null;
  expiresAt = 0;
  clearSessionHint();
  if (!fromOtherTab) {
    const message: SessionEndedMessage = { type: "session-ended", reason };
    channel?.postMessage(message);
  }
  setSnapshot({ status: "signed-out", endReason: reason, error: null });
}

async function performRefresh(): Promise<string | null> {
  try {
    const tokens = await apiRequest({
      dataId: "AUTH-004",
      logger: log,
      fn: "refreshAccessToken",
      method: "POST",
      path: "/auth/refresh",
      schema: tokenResponseSchema,
      auth: "none",
      sensitive: true,
    });
    acceptSessionTokens(tokens);
    return tokens.accessToken;
  } catch (error) {
    // Every 401 from /auth/refresh means the same thing: sign in again.
    if (isApiError(error) && error.kind === "http" && error.status === 401) {
      endSession("session-ended");
      return null;
    }
    throw error;
  }
}

/**
 * Exchanges the refresh cookie for a new access token. Callers that arrive while a
 * refresh is running share it.
 *
 * Resolves the new token, or null when the backend has ended the session. Rejects
 * with the ApiError when the refresh could not complete (offline, timeout, 5xx);
 * the session is kept, so a later attempt can still succeed.
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/**
 * Looks for a session when a signed-in page loads without one in memory: a silent
 * sign-in with the refresh cookie. Does nothing once the tab has checked.
 */
export function bootstrapSession(): void {
  if (snapshot.status !== "unknown") {
    return;
  }
  if (!hasSessionHint()) {
    // Never signed in on this browser, or signed out: nothing to refresh.
    setSnapshot({ status: "signed-out", endReason: null, error: null });
    return;
  }
  setSnapshot({ status: "checking", endReason: null, error: null });
  refreshAccessToken().catch((error: unknown) => {
    setSnapshot({
      status: "unreachable",
      endReason: null,
      error: isApiError(error) ? error : null,
    });
  });
}

/** Checks again after the backend could not be reached. */
export function retrySessionCheck(): void {
  if (snapshot.status !== "unreachable") {
    return;
  }
  setSnapshot(INITIAL_SNAPSHOT);
  bootstrapSession();
}

function isSessionEndedMessage(value: unknown): value is SessionEndedMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    value.type === "session-ended" &&
    "reason" in value &&
    isSessionEndReason(value.reason)
  );
}

/**
 * Follows sign-outs from other tabs and refreshes when the tab wakes up or comes
 * back online. Called once by the app providers; returns the cleanup.
 */
export function installAuthSession(): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  if (typeof BroadcastChannel !== "undefined") {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event: MessageEvent<unknown>) => {
      if (isSessionEndedMessage(event.data)) {
        endSession(event.data.reason, { fromOtherTab: true });
      }
    };
  }

  const refreshIfStale = (): void => {
    if (
      document.visibilityState === "visible" &&
      snapshot.status === "signed-in" &&
      !hasFreshToken()
    ) {
      refreshQuietly("resume");
    }
  };
  document.addEventListener("visibilitychange", refreshIfStale);
  window.addEventListener("online", refreshIfStale);

  return () => {
    document.removeEventListener("visibilitychange", refreshIfStale);
    window.removeEventListener("online", refreshIfStale);
    channel?.close();
    channel = null;
  };
}

// Connects the API client to this session as soon as anything imports it, before
// the first request can be sent.
registerAccessTokenProvider({
  getAccessToken: ({ forceRefresh }) => {
    if (snapshot.status === "signed-out") {
      return Promise.resolve(null);
    }
    if (!forceRefresh && hasFreshToken()) {
      return Promise.resolve(accessToken);
    }
    return refreshAccessToken();
  },
  peekAccessToken: () => accessToken,
  onSessionRejected: () => {
    endSession("session-ended");
  },
});
