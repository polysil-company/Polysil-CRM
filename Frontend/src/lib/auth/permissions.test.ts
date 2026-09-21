import { describe, expect, it } from "vitest";

import { can, PERMISSIONS, ROLE_PERMISSIONS } from "./permissions";
import { INTERNAL_ROLES, ROLES } from "./roles";

describe("[AUTH-002] role permissions", () => {
  it("shows Marketing offers to channel partners only; Admin manages them", () => {
    expect(ROLES.filter((role) => can(role, "marketing:view"))).toEqual(["channel_partner"]);
    expect(ROLES.filter((role) => can(role, "marketing:manage"))).toEqual(["admin"]);
  });

  it("shows Schemes to everyone; only Admin manages them", () => {
    expect(ROLES.every((role) => can(role, "schemes:view"))).toBe(true);
    expect(ROLES.filter((role) => can(role, "schemes:manage"))).toEqual(["admin"]);
  });

  it("keeps the single-person queues focused on their work", () => {
    expect(can("account_manager", "accounts:manage")).toBe(true);
    expect(can("dispatch_manager", "dispatch:manage")).toBe(true);
    expect(can("qa_manager", "qa:review")).toBe(true);
    for (const role of ["account_manager", "dispatch_manager", "qa_manager"] as const) {
      expect(can(role, "leads:create")).toBe(false);
    }
  });

  it("lets managers approve and assign, but not employees", () => {
    expect(can("employee", "approvals:view")).toBe(false);
    for (const role of ["district_manager", "state_manager", "regional_manager"] as const) {
      expect(can(role, "approvals:view")).toBe(true);
      expect(can(role, "leads:assign")).toBe(true);
    }
  });

  it("gives every role a dashboard and only known permissions", () => {
    for (const role of ROLES) {
      expect(can(role, "dashboard:view")).toBe(true);
      expect(ROLE_PERMISSIONS[role].every((permission) => PERMISSIONS.includes(permission))).toBe(
        true,
      );
    }
    expect(INTERNAL_ROLES).not.toContain("channel_partner");
  });
});
