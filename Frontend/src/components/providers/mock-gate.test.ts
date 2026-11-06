import { describe, expect, it, vi } from "vitest";

import { createMockReadiness } from "./mock-gate";

describe("[APP-004] mock readiness", () => {
  it("starts the worker once, on the first subscriber, and is ready only after it starts", async () => {
    const { promise, resolve } = Promise.withResolvers<void>();
    const start = vi.fn(() => promise);
    const readiness = createMockReadiness(start);
    const first = vi.fn();
    const second = vi.fn();

    readiness.subscribe(first);
    readiness.subscribe(second);

    expect(start).toHaveBeenCalledTimes(1);
    expect(readiness.isReady()).toBe(false);

    resolve();

    await vi.waitFor(() => {
      expect(readiness.isReady()).toBe(true);
    });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("keeps the app usable when the worker cannot start", async () => {
    const readiness = createMockReadiness(() => Promise.reject(new Error("no service worker")));

    readiness.subscribe(vi.fn());

    await vi.waitFor(() => {
      expect(readiness.isReady()).toBe(true);
    });
  });
});
