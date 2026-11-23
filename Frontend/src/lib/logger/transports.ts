/* eslint-disable no-console -- This file is the only place allowed to write to the console; every other module logs through createLogger(). */
import type { LogRecord, LogTransport } from "./types";

/**
 * Console transport.
 * - Server, deployed:  one JSON object per line, ready for a log collector.
 * - Server, local dev: one readable line.
 * - Browser:           a readable header line; payloads in a collapsed group.
 */
export const consoleTransport: LogTransport = {
  name: "console",
  write(record) {
    if (record.runtime === "server") {
      writeServer(record);
      return;
    }
    writeBrowser(record);
  },
};

// TODO(OBS-001): add a remote transport (Sentry / GlitchTip / OpenTelemetry collector) once
// the hosting decision is made. Browser console logs are invisible to the team unless shipped.

function headline(record: LogRecord): string {
  const dataId = record.dataId ?? "NO-DATA-ID";
  const duration = record.durationMs === undefined ? "" : ` · ${record.durationMs}ms`;
  const requestId = record.requestId === undefined ? "" : ` · req ${record.requestId}`;
  return `[${dataId}] ${record.file} → ${record.fn} → ${record.message}${duration}${requestId}`;
}

function consoleMethod(record: LogRecord): (...data: unknown[]) => void {
  switch (record.level) {
    case "error":
      return console.error;
    case "warn":
      return console.warn;
    case "info":
      return console.info;
    case "debug":
      return console.debug;
  }
}

function payloadOf(record: LogRecord): Record<string, unknown> | undefined {
  const payload: Record<string, unknown> = {};
  if (record.request !== undefined) payload.request = record.request;
  if (record.response !== undefined) payload.response = record.response;
  if (record.error !== undefined) payload.error = record.error;
  if (record.context !== undefined) payload.context = record.context;
  return Object.keys(payload).length > 0 ? payload : undefined;
}

function writeServer(record: LogRecord): void {
  const write = consoleMethod(record);
  if (record.appEnv === "development") {
    const payload = payloadOf(record);
    write(`${record.level.toUpperCase()} ${headline(record)}`, ...(payload ? [payload] : []));
    return;
  }
  write(JSON.stringify(record));
}

const LEVEL_BADGE_STYLES: Readonly<Record<LogRecord["level"], string>> = {
  debug: "color:#8a8f98;font-weight:600",
  info: "color:#0f9488;font-weight:600",
  warn: "color:#b7791f;font-weight:600",
  error: "color:#d64545;font-weight:600",
};

function writeBrowser(record: LogRecord): void {
  const label = `%c${record.level.toUpperCase()}%c ${headline(record)}`;
  const consoleCss = [LEVEL_BADGE_STYLES[record.level], "color:inherit"];
  const payload = payloadOf(record);

  if (payload === undefined) {
    consoleMethod(record)(label, ...consoleCss);
    return;
  }

  console.groupCollapsed(label, ...consoleCss);
  for (const [key, value] of Object.entries(payload)) {
    console.log(`${key}:`, value);
  }
  console.log("record:", record);
  console.groupEnd();
}
