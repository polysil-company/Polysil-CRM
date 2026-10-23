import type { DataId } from "@/lib/data-ids";
import type { AppEnv } from "@/lib/env/client";

import type { EmittableLogLevel } from "./levels";

/**
 * One structured log line.
 *
 * Reading order mirrors how an issue is traced:
 * File → Function → Request → Response (or Error).
 */
export interface LogRecord {
  readonly timestamp: string;
  readonly level: EmittableLogLevel;
  /** Source file relative to `src/`, e.g. "features/leads/api/leads.api.ts". */
  readonly file: string;
  /** Function, hook or handler that produced the record. */
  readonly fn: string;
  readonly message: string;
  readonly dataId: DataId | undefined;
  /** Correlates frontend and backend logs for one HTTP request. */
  readonly requestId: string | undefined;
  readonly durationMs: number | undefined;
  readonly request: unknown;
  readonly response: unknown;
  readonly error: unknown;
  readonly context: unknown;
  readonly runtime: "server" | "browser";
  readonly appEnv: AppEnv;
  readonly release: string;
}

/** Optional structured fields a caller can attach to a record. */
export interface LogFields {
  /** Overrides the logger's default Data ID for this record. */
  readonly dataId?: DataId;
  readonly requestId?: string;
  readonly durationMs?: number;
  readonly request?: unknown;
  readonly response?: unknown;
  readonly error?: unknown;
  readonly context?: unknown;
}

/** Destination for log records (console today; a remote sink later). */
export interface LogTransport {
  readonly name: string;
  write(record: LogRecord): void;
}
