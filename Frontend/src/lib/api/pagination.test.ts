import { describe, expect, it } from "vitest";

import { pageMetaSchema } from "./pagination";

describe("[OBS-002] page metadata", () => {
  it("reads a middle page with a counted total", () => {
    expect(
      pageMetaSchema.parse({ limit: 25, next_cursor: "abc", total: 74, total_capped: false }),
    ).toEqual({ limit: 25, nextCursor: "abc", total: 74, totalCapped: false });
  });

  it("treats an absent cursor as the last page and an absent total as not counted", () => {
    expect(pageMetaSchema.parse({ limit: 50 })).toEqual({
      limit: 50,
      nextCursor: null,
      total: null,
      totalCapped: false,
    });
  });

  it("rejects metadata that breaks the contract", () => {
    expect(pageMetaSchema.safeParse({ limit: "25" }).success).toBe(false);
    expect(pageMetaSchema.safeParse({ limit: 25, total: -1 }).success).toBe(false);
  });
});
