import {
  Analytics01Icon,
  CheckmarkBadge01Icon,
  CustomerSupportIcon,
  DashboardSquare02Icon,
  Database01Icon,
  DeliveryTruck01Icon,
  DiscountTag01Icon,
  Invoice03Icon,
  LegalDocument01Icon,
  Megaphone02Icon,
  PackageIcon,
  RupeeIcon,
  Settings02Icon,
  Store01Icon,
  Task01Icon,
  UserMultiple02Icon,
} from "@hugeicons/core-free-icons";
import type { Route } from "next";

import type { IconGlyph } from "@/components/ui/icon";
import { can, type Permission } from "@/lib/auth/permissions";
import type { Role } from "@/lib/auth/roles";
import type { DataId } from "@/lib/data-ids";

export interface NavItem {
  readonly id: string;
  readonly label: string;
  readonly icon: IconGlyph;
  /** Shown when the role has ANY of these permissions. */
  readonly permission: Permission | readonly Permission[];
  readonly dataId: DataId;
  /** Built modules have a route. Planned modules are listed (as "Soon") but are not links. */
  readonly href?: Route;
  /** A live count shown next to the label. */
  readonly countSource?: "leads";
}

export interface NavSection {
  readonly id: string;
  readonly label: string;
  readonly items: readonly NavItem[];
}

/**
 * The whole application map in one place. Order matters: moving down the
 * list animates pages forward, moving up animates them back.
 */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    id: "overview",
    label: "Overview",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        icon: DashboardSquare02Icon,
        permission: "dashboard:view",
        dataId: "RPT-001",
        href: "/dashboard",
      },
    ],
  },
  {
    id: "sales",
    label: "Sales",
    items: [
      {
        id: "leads",
        label: "Leads",
        icon: UserMultiple02Icon,
        permission: "leads:view",
        dataId: "LEAD-001",
        href: "/leads",
        countSource: "leads",
      },
      {
        id: "quotations",
        label: "Quotations",
        icon: Invoice03Icon,
        permission: "quotations:view",
        dataId: "QUOT-001",
        href: "/quotations",
      },
      {
        id: "sales-orders",
        label: "Sales orders",
        icon: PackageIcon,
        permission: "sales_orders:view",
        dataId: "SO-001",
        href: "/sales-orders",
      },
      {
        id: "approvals",
        label: "Approvals",
        icon: CheckmarkBadge01Icon,
        permission: "approvals:view",
        dataId: "APPR-001",
      },
      {
        id: "subsidy",
        label: "Subsidy",
        icon: LegalDocument01Icon,
        permission: "sales_orders:view",
        dataId: "SUBS-001",
      },
    ],
  },
  {
    id: "service",
    label: "Service",
    items: [
      {
        id: "complaints",
        label: "Complaints",
        icon: CustomerSupportIcon,
        permission: "complaints:view",
        dataId: "CMPL-001",
      },
      {
        id: "tasks",
        label: "Tasks",
        icon: Task01Icon,
        permission: "tasks:view",
        dataId: "TASK-001",
      },
    ],
  },
  {
    id: "channel",
    label: "Channel",
    items: [
      {
        id: "channel-partners",
        label: "Channel partners",
        icon: Store01Icon,
        permission: "channel_partners:view",
        dataId: "CHNL-001",
      },
      {
        id: "marketing",
        label: "Marketing",
        icon: Megaphone02Icon,
        permission: ["marketing:view", "marketing:manage"],
        dataId: "MKT-001",
      },
      {
        id: "schemes",
        label: "Schemes",
        icon: DiscountTag01Icon,
        permission: "schemes:view",
        dataId: "SCHM-001",
      },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      {
        id: "accounts",
        label: "Accounts queue",
        icon: RupeeIcon,
        permission: "accounts:manage",
        dataId: "ACCT-001",
      },
      {
        id: "dispatch",
        label: "Dispatch queue",
        icon: DeliveryTruck01Icon,
        permission: "dispatch:manage",
        dataId: "DISP-001",
      },
    ],
  },
  {
    id: "admin",
    label: "Admin",
    items: [
      {
        id: "reports",
        label: "Reports",
        icon: Analytics01Icon,
        permission: "reports:view",
        dataId: "RPT-002",
      },
      {
        id: "masters",
        label: "Masters",
        icon: Database01Icon,
        permission: "masters:manage",
        dataId: "MSTR-001",
      },
      {
        id: "users",
        label: "Users & roles",
        icon: Settings02Icon,
        permission: "users:manage",
        dataId: "ADMN-001",
      },
    ],
  },
];

export function canSeeNavItem(item: NavItem, role: Role): boolean {
  const required: readonly Permission[] =
    typeof item.permission === "string" ? [item.permission] : item.permission;
  return required.some((permission) => can(role, permission));
}

/** Sections and items the role may see; empty sections are dropped. */
export function visibleNavSections(role: Role): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canSeeNavItem(item, role)),
  })).filter((section) => section.items.length > 0);
}

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  if (item.href === undefined) {
    return false;
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export function findActiveNavItem(pathname: string): NavItem | undefined {
  return NAV_SECTIONS.flatMap((section) => section.items).find((item) =>
    isNavItemActive(item, pathname),
  );
}
