import type { AppEnv } from "@/lib/env/client";

/**
 * Log levels, lowest to highest. `silent` switches logging off entirely.
 * The active level is resolved at runtime — see `runtime-level.ts`.
 */
export const LOG_LEVELS = ["debug", "info", "warn", "error", "silent"] as const;

export type LogLevel = (typeof LOG_LEVELS)[number];

/** Levels a record can be written at (`silent` is only a threshold). */
export type EmittableLogLevel = Exclude<LogLevel, "silent">;

const LEVEL_RANK: Readonly<Record<LogLevel, number>> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
  silent: 100,
};

/** Cookie the proxy writes so browsers pick up the server's LOG_LEVEL without a rebuild. */
export const LOG_LEVEL_COOKIE = "polysil-log-level";

/** Per-browser override, set from the console: `polysilLogger.setLevel("debug")`. */
export const LOG_LEVEL_STORAGE_KEY = "polysil:log-level";

export function isLogLevel(value: unknown): value is LogLevel {
  return LOG_LEVELS.some((level) => level === value);
}

/** True when a record at `level` passes the `threshold`. */
export function shouldLog(level: EmittableLogLevel, threshold: LogLevel): boolean {
  return LEVEL_RANK[level] >= LEVEL_RANK[threshold];
}

/** Level used when LOG_LEVEL is not configured. */
export function defaultLogLevel(appEnv: AppEnv): LogLevel {
  switch (appEnv) {
    case "development":
    case "feature":
      return "debug";
    case "staging":
      return "info";
    case "production":
      return "warn";
  }
}
