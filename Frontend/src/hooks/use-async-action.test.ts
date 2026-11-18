import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createLogger } from "@/lib/logger";

import { ASYNC_ACTION_TIMING, useAsyncAction } from "./use-async-action";

const log = createLogger({ file: "hooks/use-async-action.test.ts", dataId: "DS-001" });

describe("[DS-001] useAsyncAction", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("moves loading → success → idle and returns the result", async () => {
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useAsyncAction({
        action: (value: number) => Promise.resolve(value * 2),
        logger: log,
        fn: "double",
        onSuccess,
      }),
    );

    let pending: Promise<number | undefined> = Promise.resolve(undefined);
    act(() => {
      pending = result.current.run(21);
    });
    expect(result.current.state).toBe("loading");
    expect(result.current.isBusy).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.minLoadingMs);
    });
    await expect(pending).resolves.toBe(42);
    expect(result.current.state).toBe("success");
    expect(onSuccess).toHaveBeenCalledWith(42);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.successMs);
    });
    expect(result.current.state).toBe("idle");
  });

  it("moves loading → error → idle without throwing", async () => {
    const failure = new Error("nope");
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useAsyncAction({ action: () => Promise.reject(failure), logger: log, fn: "fail", onError }),
    );

    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = result.current.run();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.minLoadingMs);
    });

    await expect(pending).resolves.toBeUndefined();
    expect(result.current.state).toBe("error");
    expect(result.current.error).toBe(failure);
    expect(onError).toHaveBeenCalledWith(failure);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.errorMs);
    });
    expect(result.current.state).toBe("idle");
  });

  it("ignores a second run while one is in flight", async () => {
    const action = vi.fn(() => Promise.resolve("done"));
    const { result } = renderHook(() => useAsyncAction({ action, logger: log, fn: "once" }));

    let second: Promise<string | undefined> = Promise.resolve(undefined);
    act(() => {
      void result.current.run();
      second = result.current.run();
    });

    await expect(second).resolves.toBeUndefined();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.minLoadingMs);
    });
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("reset returns to idle immediately", async () => {
    const { result } = renderHook(() =>
      useAsyncAction({ action: () => Promise.reject(new Error("x")), logger: log, fn: "reset" }),
    );

    act(() => {
      void result.current.run();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ASYNC_ACTION_TIMING.minLoadingMs);
    });
    expect(result.current.state).toBe("error");

    act(() => {
      result.current.reset();
    });
    expect(result.current.state).toBe("idle");
    expect(result.current.error).toBeUndefined();
  });
});
