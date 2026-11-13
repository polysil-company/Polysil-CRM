import { clientEnv } from "@/lib/env/client";

import {
  defaultLogLevel,
  isLogLevel,
  LOG_LEVEL_COOKIE,
  LOG_LEVEL_STORAGE_KEY,
  type LogLevel,
} from "./levels";

/**
 * Resolves the active log level at runtime — no rebuild needed to change it.
 *
 * Server:  LOG_LEVEL env var (read on every call), else the environment default.
 * Browser: 1. localStorage override (this browser only, for live debugging)
 *          2. `polysil-log-level` cookie, written by `src/proxy.ts` from LOG_LEVEL
 *          3. the environment default
 *
 * So flipping LOG_LEVEL on the host (and restarting the container) changes
 * logging for the server AND every browser on its next navigation.
 */

export function resolveServerLogLevel(): LogLevel {
  // Deliberately NOT a NEXT_PUBLIC_ variable: it is read at runtime, never inlined at build.
  const configured = process.env.LOG_LEVEL;
  return isLogLevel(configured) ? configured : defaultLogLevel(clientEnv.appEnv);
}

function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return undefined;
}

function readStorageOverride(): string | null {
  try {
    return window.localStorage.getItem(LOG_LEVEL_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (privacy mode, blocked site data).
    return null;
  }
}

/** This browser's override, or null when it follows the server's LOG_LEVEL. */
export function readBrowserLogLevelOverride(): LogLevel | null {
  const override = readStorageOverride();
  return isLogLevel(override) ? override : null;
}

export function resolveBrowserLogLevel(): LogLevel {
  const override = readStorageOverride();
  if (isLogLevel(override)) {
    return override;
  }
  const cookie = readCookie(LOG_LEVEL_COOKIE);
  if (isLogLevel(cookie)) {
    return cookie;
  }
  return defaultLogLevel(clientEnv.appEnv);
}

export function resolveLogLevel(): LogLevel {
  return typeof window === "undefined" ? resolveServerLogLevel() : resolveBrowserLogLevel();
}

/** Sets (or clears, with `null`) this browser's log level override. */
export function setBrowserLogLevelOverride(level: LogLevel | null): void {
  try {
    if (level === null) {
      window.localStorage.removeItem(LOG_LEVEL_STORAGE_KEY);
    } else {
      window.localStorage.setItem(LOG_LEVEL_STORAGE_KEY, level);
    }
  } catch {
    // Storage unavailable — the cookie/default level keeps applying.
  }
}
