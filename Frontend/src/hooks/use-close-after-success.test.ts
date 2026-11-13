import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLOSE_AFTER_SUCCESS_MS, useCloseAfterSuccess } from "./use-close-after-success";

describe("[APP-003] useCloseAfterSuccess", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("closes the dialog a moment after a save", () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useCloseAfterSuccess(onClose));

    result.current();
    vi.advanceTimersByTime(CLOSE_AFTER_SUCCESS_MS - 1);
    expect(onClose).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("forgets the close when the dialog goes first", () => {
    const onClose = vi.fn();
    const { result, unmount } = renderHook(() => useCloseAfterSuccess(onClose));

    result.current();
    unmount();
    vi.advanceTimersByTime(CLOSE_AFTER_SUCCESS_MS * 2);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("starts nothing when a save finishes after the dialog has gone", () => {
    const onClose = vi.fn();
    const { result, unmount } = renderHook(() => useCloseAfterSuccess(onClose));
    const closeSoon = result.current;

    unmount();
    // A save that resolves later still calls its success handler.
    closeSoon();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(CLOSE_AFTER_SUCCESS_MS * 2);
    expect(onClose).not.toHaveBeenCalled();
  });
});
