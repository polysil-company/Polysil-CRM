import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ModulePermission } from "@/lib/auth/permissions";
import { mockPermissionsFor } from "@/mocks/data/permissions";

import {
  canOpenPath,
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
    ).toEqual(["dashboard", "leads", "customers"]);
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
      description: "Leads, quotations, orders and service at a glance.",
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

describe("[APP-006] route guards", () => {
  const dealer = mockPermissionsFor("dealer");
  const admin = mockPermissionsFor("admin");

  it("keeps a partner user out of the staff pages they could open by URL (F-8)", () => {
    for (const path of ["/approval-limits", "/qr-codes", "/dispatch", "/tasks", "/messages"]) {
      expect(canOpenPath(path, dealer, "partner_user")).toBe(false);
    }
    expect(canOpenPath("/leads/duplicates", dealer, "partner_user")).toBe(false);
  });

  it("lets a partner user open their own pages, and the pages under them", () => {
    expect(canOpenPath("/leads", dealer, "partner_user")).toBe(true);
    expect(canOpenPath("/leads/lead-10001", dealer, "partner_user")).toBe(true);
    expect(canOpenPath("/sales-orders", dealer, "partner_user")).toBe(true);
    expect(canOpenPath("/dashboard", dealer, "partner_user")).toBe(true);
  });

  it("lets staff with the permission in, and keeps out staff without it", () => {
    expect(canOpenPath("/approval-limits", admin, "staff")).toBe(true);
    expect(canOpenPath("/leads/duplicates", admin, "staff")).toBe(true);
    expect(canOpenPath("/approval-limits", mockPermissionsFor("employee"), "staff")).toBe(false);
    expect(canOpenPath("/approvals", mockPermissionsFor("employee"), "staff")).toBe(false);
  });

  it("opens Channel partners and the pages under it to staff who read partners only (CHNL-001)", () => {
    expect(canOpenPath("/partners", mockPermissionsFor("employee"), "staff")).toBe(true);
    expect(canOpenPath("/partners/new", admin, "staff")).toBe(true);
    expect(canOpenPath("/partners/p-1/edit", dealer, "partner_user")).toBe(false);
    expect(canOpenPath("/partners", mockPermissionsFor("qa_manager"), "staff")).toBe(false);
  });

  it("opens the Accounts queue to whoever may view payments, as the backend names it (ACCT-001)", () => {
    expect(canOpenPath("/accounts", mockPermissionsFor("account_manager"), "staff")).toBe(true);
    expect(canOpenPath("/accounts", admin, "staff")).toBe(true);
    expect(canOpenPath("/accounts", mockPermissionsFor("employee"), "staff")).toBe(false);
    expect(canOpenPath("/accounts", dealer, "partner_user")).toBe(false);
  });

  it("leaves pages outside the nav map open", () => {
    expect(canOpenPath("/account", [], "partner_user")).toBe(true);
  });
});

describe("[APP-007] the release's menu", () => {
  const admin = mockPermissionsFor("admin");
  const released = ["dashboard", "leads", "quotations", "products"];

  it("shows only the released screens, whatever the permissions allow", () => {
    const ids = visibleNavSections(admin, "staff", released).flatMap((section) =>
      section.items.map((item) => item.id),
    );
    expect(ids).toEqual(["dashboard", "leads", "quotations", "products"]);
  });

  it("still applies the permissions inside the release", () => {
    const ids = visibleNavSections([], "staff", released).flatMap((section) =>
      section.items.map((item) => item.id),
    );
    expect(ids).toEqual(["dashboard"]);
  });

  it("refuses a screen outside the release by its address too", () => {
    expect(canOpenPath("/qr-codes", admin, "staff", released)).toBe(false);
    expect(canOpenPath("/subsidy-masters", admin, "staff", released)).toBe(false);
    expect(canOpenPath("/products/price-lists/pl-1", admin, "staff", released)).toBe(true);
    expect(canOpenPath("/account", admin, "staff", released)).toBe(true);
  });

  it("releases everything when no list is set", () => {
    expect(canOpenPath("/qr-codes", admin, "staff", null)).toBe(true);
  });

  it("knows every id the deploy script releases", () => {
    // The deploy script builds the client's frontend with NEXT_PUBLIC_NAV_ONLY=<RELEASED_NAV>;
    // an id that matches no item would silently hide that screen.
    const script = readFileSync(
      resolve(__dirname, "../../../../backend/scripts/deploy_staging.py"),
      "utf8",
    );
    const list = /RELEASED_NAV = \(([^)]*)\)/.exec(script)?.[1] ?? "";
    const ids = [...list.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
    const known = new Set(NAV_SECTIONS.flatMap((section) => section.items.map((item) => item.id)));

    expect(ids.length).toBeGreaterThan(0);
    expect(ids.filter((id) => id === undefined || !known.has(id))).toEqual([]);
  });
});
