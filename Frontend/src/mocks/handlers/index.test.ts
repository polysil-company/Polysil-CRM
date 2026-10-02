import { describe, expect, it } from "vitest";

import { handlers, unbuiltHandlers } from "./index";

function paths(list: typeof handlers): string[] {
  return list.map((handler) => String(handler.info.path));
}

describe("[APP-004] mock handler sets", () => {
  it("leaves every connected module to the real API in partial mode", () => {
    for (const fragment of [
      "/auth/",
      "/leads",
      "/lookups/",
      "/dashboard/",
      "/notifications",
      "/conversations",
      "/staff-directory",
    ]) {
      expect(
        paths(unbuiltHandlers).some((path) => path.includes(fragment)),
        fragment,
      ).toBe(false);
      expect(
        paths(handlers).some((path) => path.includes(fragment)),
        fragment,
      ).toBe(true);
    }
  });

  it("mocks nothing in partial mode now that every screen is connected", () => {
    expect(unbuiltHandlers).toEqual([]);
  });
});
