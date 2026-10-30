import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "./use-debounced-value";

describe("[MSTR-002] useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("passes a value on only once it has stopped changing", () => {
    const hook = renderHook(({ value }) => useDebouncedValue(value, 250), {
      initialProps: { value: "g" },
    });

    hook.rerender({ value: "go" });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    hook.rerender({ value: "gon" });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(hook.result.current).toBe("g");

    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(hook.result.current).toBe("gon");
  });
});
