import { describe, expect, it } from "vitest";

import { handlers, unbuiltHandlers } from "./index";

function paths(list: typeof handlers): string[] {
  return list.map((handler) => String(handler.info.path));
}

describe("[APP-004] mock handler sets", () => {
  it("leaves sign-in, leads, lookups and the dashboard to the real API in partial mode", () => {
    for (const fragment of ["/auth/", "/leads", "/lookups/", "/dashboard/"]) {
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

  it("still mocks the modules the backend does not serve yet", () => {
    for (const endpoint of ["/notifications", "/conversations"]) {
      expect(
        paths(unbuiltHandlers).some((path) => path.endsWith(endpoint)),
        endpoint,
      ).toBe(true);
    }
  });
});
