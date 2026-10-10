import { describe, expect, it } from "vitest";

import { meResponseSchema } from "./session.schemas";

describe("[AUTH-002] GET /auth/me contract", () => {
  it("turns the backend's response into the session screens read", () => {
    const session = meResponseSchema.parse({
      data: {
        id: "0b7c",
        full_name: "Asha Mehta",
        user_type: "staff",
        role: { code: "district_manager", name: "District Manager" },
        org_unit: { id: "ou-1", name: "Vadodara District" },
        partner: null,
        permissions: [{ module: "leads", actions: ["view", "create"], scope: "org_subtree" }],
      },
    });

    expect(session).toEqual({
      user: { id: "0b7c", name: "Asha Mehta" },
      userType: "staff",
      role: { code: "district_manager", name: "District Manager" },
      orgUnit: { id: "ou-1", name: "Vadodara District" },
      partner: null,
      permissions: [{ module: "leads", actions: ["view", "create"], scope: "org_subtree" }],
      mustChangePassword: false,
    });
  });

  it("treats missing optional fields as empty", () => {
    const session = meResponseSchema.parse({
      data: {
        id: "c-9",
        full_name: "Kiran Patel",
        user_type: "consumer",
        partner: { id: "prt-1" },
        permissions: [{ module: "schemes", actions: ["view"] }],
      },
    });

    expect(session.role).toBeNull();
    expect(session.orgUnit).toBeNull();
    expect(session.partner).toEqual({ id: "prt-1", name: null });
    expect(session.permissions).toEqual([{ module: "schemes", actions: ["view"], scope: null }]);
    expect(session.mustChangePassword).toBe(false);
  });

  it("[AUTH-007] reads a temporary password in force", () => {
    const session = meResponseSchema.parse({
      data: {
        id: "u-1",
        full_name: "Asha Patel",
        user_type: "staff",
        must_change_password: true,
      },
    });
    expect(session.mustChangePassword).toBe(true);
  });

  it("rejects a response without the envelope or with an unknown user type", () => {
    expect(
      meResponseSchema.safeParse({ id: "1", full_name: "A", user_type: "staff" }).success,
    ).toBe(false);
    expect(
      meResponseSchema.safeParse({ data: { id: "1", full_name: "A", user_type: "guest" } }).success,
    ).toBe(false);
  });
});
