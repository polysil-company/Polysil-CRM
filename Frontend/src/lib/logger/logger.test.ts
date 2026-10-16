import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  createLogger,
  defaultLogLevel,
  isLogLevel,
  registerLogTransport,
  setBrowserLogLevelOverride,
  shouldLog,
  type LogRecord,
} from "@/lib/logger";

describe("[OBS-001] log levels", () => {
  it("passes records at or above the threshold", () => {
    expect(shouldLog("error", "warn")).toBe(true);
    expect(shouldLog("warn", "warn")).toBe(true);
    expect(shouldLog("info", "warn")).toBe(false);
    expect(shouldLog("error", "silent")).toBe(false);
  });

  it("defaults to verbose locally and quiet in production", () => {
    expect(defaultLogLevel("development")).toBe("debug");
    expect(defaultLogLevel("feature")).toBe("debug");
    expect(defaultLogLevel("staging")).toBe("info");
    expect(defaultLogLevel("production")).toBe("warn");
  });

  it("recognises valid levels only", () => {
    expect(isLogLevel("debug")).toBe(true);
    expect(isLogLevel("verbose")).toBe(false);
    expect(isLogLevel(null)).toBe(false);
  });
});

describe("[OBS-001] createLogger", () => {
  const records: LogRecord[] = [];
  let unregister = (): void => undefined;

  beforeEach(() => {
    records.length = 0;
    setBrowserLogLevelOverride("debug");
    unregister = registerLogTransport({
      name: "capture",
      write: (record) => {
        records.push(record);
      },
    });
  });

  afterEach(() => {
    unregister();
  });

  const log = createLogger({ file: "features/leads/api/leads.api.ts", dataId: "LEAD-001" });

  it("writes File → Function → message with the logger's Data ID", () => {
    log.info("listLeads", "loaded", { context: { rows: 2 } });

    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      level: "info",
      file: "features/leads/api/leads.api.ts",
      fn: "listLeads",
      message: "loaded",
      dataId: "LEAD-001",
      runtime: "browser",
      context: { rows: 2 },
    });
  });

  it("lets a record or a derived logger use a different Data ID", () => {
    log.info("fn", "override", { dataId: "LEAD-002" });
    log.withDataId("LEAD-003").info("fn", "derived");

    expect(records.map((record) => record.dataId)).toEqual(["LEAD-002", "LEAD-003"]);
  });

  it("drops records below the active level, and everything when silent", () => {
    setBrowserLogLevelOverride("warn");
    log.debug("fn", "hidden");
    log.info("fn", "hidden");
    log.warn("fn", "shown");
    log.error("fn", "shown");
    expect(records.map((record) => record.level)).toEqual(["warn", "error"]);

    setBrowserLogLevelOverride("silent");
    log.error("fn", "hidden");
    expect(records).toHaveLength(2);
  });

  it("redacts payloads before any transport sees them", () => {
    log.info("fn", "request", { request: { phone: "+919812345678", password: "hunter2" } });

    expect(records[0]?.request).toEqual({ phone: "******5678", password: "[REDACTED]" });
  });

  it("traces a successful action with its duration and returns the result", async () => {
    await expect(log.trace("load", () => Promise.resolve(42))).resolves.toBe(42);

    expect(records.map((record) => record.message)).toEqual(["start", "success"]);
    expect(records[1]?.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("traces a failure at error level and re-throws it", async () => {
    await expect(log.trace("save", () => Promise.reject(new Error("boom")))).rejects.toThrow(
      "boom",
    );

    expect(records.at(-1)).toMatchObject({ level: "error", message: "failed" });
  });

  it("traces a cancellation at debug level", async () => {
    const aborted = new DOMException("The operation was aborted", "AbortError");
    await expect(log.trace("load", () => Promise.reject(aborted))).rejects.toBe(aborted);

    expect(records.at(-1)).toMatchObject({ level: "debug", message: "aborted" });
  });

  it("keeps working when a transport throws", () => {
    const removeBroken = registerLogTransport({
      name: "broken",
      write: () => {
        throw new Error("transport down");
      },
    });

    expect(() => {
      log.error("fn", "still fine");
    }).not.toThrow();
    expect(records).toHaveLength(1);

    removeBroken();
  });
});
