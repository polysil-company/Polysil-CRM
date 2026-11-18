import type { DataId } from "@/lib/data-ids";
import { clientEnv } from "@/lib/env/client";

import { shouldLog, type EmittableLogLevel } from "./levels";
import { redact } from "./redact";
import { resolveLogLevel } from "./runtime-level";
import { consoleTransport } from "./transports";
import type { LogFields, LogRecord, LogTransport } from "./types";

export interface LoggerScope {
  /**
   * Path of the calling file relative to `src/`, e.g. "features/leads/api/leads.api.ts".
   * Enforced by the `local/logger-file-matches` ESLint rule, so it cannot drift.
   */
  readonly file: string;
  /** Default Data ID for every record from this logger. */
  readonly dataId?: DataId;
}

export interface TraceOptions extends LogFields {
  /** Include the resolved value in the success record (debug level only). Default false. */
  readonly logResult?: boolean;
}

export interface Logger {
  debug(fn: string, message: string, fields?: LogFields): void;
  info(fn: string, message: string, fields?: LogFields): void;
  warn(fn: string, message: string, fields?: LogFields): void;
  error(fn: string, message: string, fields?: LogFields): void;
  /** Cheap check before building an expensive payload. */
  isLevelEnabled(level: EmittableLogLevel): boolean;
  /**
   * Runs an async action and logs start (debug), success (info) or failure
   * (error) with its duration. Aborts are logged at debug and re-thrown.
   */
  trace<T>(fn: string, run: () => Promise<T>, options?: TraceOptions): Promise<T>;
  /** Same logger, different default Data ID. */
  withDataId(dataId: DataId): Logger;
}

const transports = new Set<LogTransport>([consoleTransport]);

/**
 * Adds a transport (e.g. a remote sink, or a capture transport in tests).
 * Returns a function that removes it again.
 */
export function registerLogTransport(transport: LogTransport): () => void {
  transports.add(transport);
  return () => {
    transports.delete(transport);
  };
}

/** Removes the default console transport. For tests that assert on captured records. */
export function removeConsoleTransport(): () => void {
  transports.delete(consoleTransport);
  return () => {
    transports.add(consoleTransport);
  };
}

export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

export function elapsedMs(startedAt: number): number {
  return Math.round(performance.now() - startedAt);
}

export function createLogger(scope: LoggerScope): Logger {
  const runtime: LogRecord["runtime"] = typeof window === "undefined" ? "server" : "browser";

  function emit(level: EmittableLogLevel, fn: string, message: string, fields?: LogFields): void {
    if (!shouldLog(level, resolveLogLevel())) {
      return;
    }

    const record: LogRecord = {
      timestamp: new Date().toISOString(),
      level,
      file: scope.file,
      fn,
      message,
      dataId: fields?.dataId ?? scope.dataId,
      requestId: fields?.requestId,
      durationMs: fields?.durationMs,
      request: redact(fields?.request),
      response: redact(fields?.response),
      error: redact(fields?.error),
      context: redact(fields?.context),
      runtime,
      appEnv: clientEnv.appEnv,
      release: clientEnv.release,
    };

    for (const transport of transports) {
      try {
        transport.write(record);
      } catch {
        // A broken transport must never break the application.
      }
    }
  }

  const logger: Logger = {
    debug: (fn, message, fields) => emit("debug", fn, message, fields),
    info: (fn, message, fields) => emit("info", fn, message, fields),
    warn: (fn, message, fields) => emit("warn", fn, message, fields),
    error: (fn, message, fields) => emit("error", fn, message, fields),

    isLevelEnabled: (level) => shouldLog(level, resolveLogLevel()),

    async trace(fn, run, options = {}) {
      const { logResult = false, ...fields } = options;
      const startedAt = performance.now();
      emit("debug", fn, "start", fields);

      try {
        const result = await run();
        emit("info", fn, "success", {
          ...fields,
          durationMs: elapsedMs(startedAt),
          ...(logResult && logger.isLevelEnabled("debug") ? { response: result } : {}),
        });
        return result;
      } catch (error) {
        const durationMs = elapsedMs(startedAt);
        if (isAbortError(error)) {
          emit("debug", fn, "aborted", { ...fields, durationMs });
        } else {
          emit("error", fn, "failed", { ...fields, durationMs, error });
        }
        throw error;
      }
    },

    withDataId: (dataId) => createLogger({ ...scope, dataId }),
  };

  return logger;
}
