import { isLogLevel, type LogLevel } from "./levels";
import { resolveBrowserLogLevel, setBrowserLogLevelOverride } from "./runtime-level";

export interface LoggerDevtools {
  getLevel: () => LogLevel;
  /** Pass null to clear this browser's override and follow LOG_LEVEL again. */
  setLevel: (level: LogLevel | null) => void;
  help: () => string;
}

declare global {
  interface Window {
    polysilLogger?: LoggerDevtools;
  }
}

/**
 * Exposes `window.polysilLogger` for live debugging in any environment:
 *   polysilLogger.setLevel("debug")   // this browser only
 *   polysilLogger.setLevel(null)      // back to the server-controlled level
 */
export function installLoggerDevtools(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.polysilLogger = {
    getLevel: resolveBrowserLogLevel,
    setLevel: (level) => {
      if (level === null || isLogLevel(level)) {
        setBrowserLogLevelOverride(level);
      }
    },
    help: () =>
      'polysilLogger.setLevel("debug" | "info" | "warn" | "error" | "silent" | null) — null clears the override.',
  };
}
