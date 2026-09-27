import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useIdempotencyKey } from "./use-idempotency-key";

describe("[OBS-002] useIdempotencyKey", () => {
  it("keeps one key for the same body and makes a new one when the body changes", () => {
    const { result } = renderHook(() => useIdempotencyKey());

    const first = result.current.keyFor({ note: "Called" });
    expect(result.current.keyFor({ note: "Called" })).toBe(first);

    const changed = result.current.keyFor({ note: "Called twice" });
    expect(changed).not.toBe(first);
    expect(result.current.keyFor({ note: "Called" })).not.toBe(first);
  });

  it("starts over after reset, so the next save is a new request", () => {
    const { result } = renderHook(() => useIdempotencyKey());

    const first = result.current.keyFor({ to_stage: "contacted" });
    result.current.reset();

    expect(result.current.keyFor({ to_stage: "contacted" })).not.toBe(first);
  });

  it("keeps the key across renders", () => {
    const { result, rerender } = renderHook(() => useIdempotencyKey());

    const first = result.current.keyFor({ a: 1 });
    rerender();

    expect(result.current.keyFor({ a: 1 })).toBe(first);
  });
});
