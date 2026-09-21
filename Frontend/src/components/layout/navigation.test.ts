import { describe, expect, it } from "vitest";

import type { ModulePermission } from "@/lib/auth/permissions";
import { mockPermissionsFor } from "@/mocks/data/permissions";

import {
  findActiveNavItem,
  findPageHeading,
  isNavItemActive,
  NAV_SECTIONS,
  visibleNavSections,
} from "./navigation";

function visibleIds(
  permissions: readonly ModulePermission[],
  userType: string | null = null,
): string[] {
  return visibleNavSections(permissions, userType).flatMap((section) =>
    section.items.map((item) => item.id),
  );
}

describe("[APP-001] navigation", () => {
  it("shows the modules the user may view, and the dashboard to everyone", () => {
    expect(
      visibleIds([{ module: "leads", actions: ["view", "create"], scope: "org_subtree" }]),
    ).toEqual(["dashboard", "leads"]);
    expect(visibleIds([])).toEqual(["dashboard"]);
  });

  it("needs the view action, not just any grant", () => {
    expect(visibleIds([{ module: "leads", actions: ["create"], scope: null }])).toEqual([
      "dashboard",
    ]);
  });

  it("ignores modules the app does not know yet", () => {
    expect(visibleIds([{ module: "warehouse", actions: ["view"], scope: "global" }])).toEqual([
      "dashboard",
    ]);
  });

  it("shows a dealer their own set of modules", () => {
    const ids = visibleIds(mockPermissionsFor("dealer"));
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

  it("drops sections that end up empty", () => {
    const sections = visibleNavSections(mockPermissionsFor("dispatch_manager"));
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

  it("gives every item a Data ID", () => {
    for (const item of NAV_SECTIONS.flatMap((section) => section.items)) {
      expect(item.dataId).toMatch(/^[A-Z]{2,6}-\d{3}$/);
    }
  });
});

describe("[MSG-001] Messages in navigation", () => {
  it("shows Messages to staff only", () => {
    expect(visibleIds([], "staff")).toContain("messages");
    expect(visibleIds([], "partner_user")).not.toContain("messages");
    expect(visibleIds([])).not.toContain("messages");
  });
});

describe("[APP-005] page headings in the top bar", () => {
  it("uses the section's title, with its description only on the section's own page", () => {
    expect(findPageHeading("/dashboard")).toEqual({
      title: "Dashboard",
      description: "Your territory at a glance.",
    });
    expect(findPageHeading("/leads/lead-10001")).toEqual({ title: "Leads" });
    expect(findPageHeading("/unknown")).toEqual({ title: "Polysil CRM" });
  });

  it("gives every built page a description, since pages no longer show one", () => {
    const built = NAV_SECTIONS.flatMap((section) => section.items).filter(
      (item) => item.href !== undefined,
    );
    for (const item of built) {
      expect(item.description?.length ?? 0).toBeGreaterThan(0);
    }
  });
});
