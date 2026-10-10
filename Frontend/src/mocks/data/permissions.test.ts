import { describe, expect, it } from "vitest";

import { can, canApprove } from "@/lib/auth/permissions";
import { PARTNER_ROLES, ROLES, STAFF_ROLES } from "@/lib/auth/roles";

import { mockPermissionsFor } from "./permissions";

describe("[AUTH-002] mock permission matrix", () => {
  it("shows Marketing offers to channel partners; only Admin manages them", () => {
    const viewers = ROLES.filter((role) => can(mockPermissionsFor(role), "marketing"));
    expect(viewers).toEqual([...(["admin"] as const), ...PARTNER_ROLES]);
    expect(ROLES.filter((role) => can(mockPermissionsFor(role), "marketing", "edit"))).toEqual([
      "admin",
    ]);
  });

  it("shows Schemes to everyone; only Admin manages them", () => {
    expect(ROLES.every((role) => can(mockPermissionsFor(role), "schemes"))).toBe(true);
    expect(ROLES.filter((role) => can(mockPermissionsFor(role), "schemes", "edit"))).toEqual([
      "admin",
    ]);
  });

  it("keeps the single-person queues focused on their work", () => {
    expect(can(mockPermissionsFor("account_manager"), "accounts", "approve")).toBe(true);
    expect(can(mockPermissionsFor("dispatch_manager"), "dispatch", "edit")).toBe(true);
    expect(can(mockPermissionsFor("qa_manager"), "complaints", "approve")).toBe(true);
    for (const role of ["account_manager", "dispatch_manager", "qa_manager"] as const) {
      expect(can(mockPermissionsFor(role), "leads", "create")).toBe(false);
    }
  });

  it("lets managers, Accounts and Dispatch approve, but not employees or channel partners", () => {
    expect(canApprove(mockPermissionsFor("employee"))).toBe(false);
    for (const role of [
      "district_manager",
      "state_manager",
      "regional_manager",
      "account_manager",
      "dispatch_manager",
    ] as const) {
      expect(can(mockPermissionsFor(role), "sales_orders", "approve")).toBe(true);
    }
    for (const role of PARTNER_ROLES) {
      expect(canApprove(mockPermissionsFor(role))).toBe(false);
    }
  });

  it("gives each module one entry, as GET /auth/me does", () => {
    for (const role of ["district_manager", "employee", "dealer"] as const) {
      const modules = mockPermissionsFor(role).map((entry) => entry.module);
      expect(new Set(modules).size).toBe(modules.length);
    }
  });

  it("never lets a channel partner into staff administration", () => {
    for (const role of PARTNER_ROLES) {
      const permissions = mockPermissionsFor(role);
      expect(can(permissions, "users")).toBe(false);
      expect(can(permissions, "masters")).toBe(false);
      expect(can(permissions, "quotations")).toBe(false);
    }
    expect(STAFF_ROLES).not.toContain("dealer");
  });
});
