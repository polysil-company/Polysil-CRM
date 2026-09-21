import { describe, expect, it } from "vitest";

import { can, type ModulePermission } from "./permissions";

const permissions: readonly ModulePermission[] = [
  { module: "leads", actions: ["view", "create"], scope: "org_subtree" },
  { module: "orders", actions: ["view"], scope: null },
];

describe("[AUTH-002] can", () => {
  it("checks the view action by default", () => {
    expect(can(permissions, "leads")).toBe(true);
    expect(can(permissions, "quotations")).toBe(false);
  });

  it("checks a specific action", () => {
    expect(can(permissions, "leads", "create")).toBe(true);
    expect(can(permissions, "leads", "edit")).toBe(false);
    expect(can(permissions, "orders", "create")).toBe(false);
  });

  it("is not confused by actions the app does not know", () => {
    expect(can([{ module: "leads", actions: ["export", "view"], scope: null }], "leads")).toBe(
      true,
    );
  });

  it("grants nothing without permissions", () => {
    expect(can([], "leads")).toBe(false);
  });
});
