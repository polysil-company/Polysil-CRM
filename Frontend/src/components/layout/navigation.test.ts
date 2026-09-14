import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/auth/roles";

import { findActiveNavItem, isNavItemActive, NAV_SECTIONS, visibleNavSections } from "./navigation";

function visibleIds(role: Role): string[] {
  return visibleNavSections(role).flatMap((section) => section.items.map((item) => item.id));
}

describe("[APP-001] navigation", () => {
  it("shows channel partners their own set of modules", () => {
    const ids = visibleIds("channel_partner");
    expect(ids).toEqual(
      expect.arrayContaining([
        "dashboard",
        "leads",
        "sales-orders",
        "complaints",
        "marketing",
        "schemes",
      ]),
    );
    expect(ids).not.toContain("approvals");
    expect(ids).not.toContain("quotations");
    expect(ids).not.toContain("users");
  });

  it("shows Marketing to channel partners and to Admin (who manages it), not to other staff", () => {
    expect(visibleIds("admin")).toContain("marketing");
    expect(visibleIds("employee")).not.toContain("marketing");
    expect(visibleIds("state_manager")).not.toContain("marketing");
  });

  it("shows Schemes to every role", () => {
    for (const role of ["employee", "admin", "qa_manager", "channel_partner"] as const) {
      expect(visibleIds(role)).toContain("schemes");
    }
  });

  it("drops sections that end up empty", () => {
    const sections = visibleNavSections("dispatch_manager");
    expect(sections.every((section) => section.items.length > 0)).toBe(true);
    expect(sections.map((section) => section.id)).not.toContain("admin");
  });

  it("marks parents active for nested routes", () => {
    const leads = NAV_SECTIONS.flatMap((section) => section.items).find(
      (item) => item.id === "leads",
    );
    expect(leads && isNavItemActive(leads, "/leads/lead-10001")).toBe(true);
    expect(leads && isNavItemActive(leads, "/leadsboard")).toBe(false);
    expect(findActiveNavItem("/dashboard")?.id).toBe("dashboard");
    expect(findActiveNavItem("/unknown")).toBeUndefined();
  });

  it("gives every built module a Data ID and every planned one no route", () => {
    for (const item of NAV_SECTIONS.flatMap((section) => section.items)) {
      expect(item.dataId).toMatch(/^[A-Z]{2,6}-\d{3}$/);
    }
  });
});
