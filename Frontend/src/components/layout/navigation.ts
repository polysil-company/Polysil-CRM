import {
  Analytics01Icon,
  BubbleChatIcon,
  CheckmarkBadge01Icon,
  Clock01Icon,
  CustomerSupportIcon,
  DashboardSquare02Icon,
  Database01Icon,
  DeliveryTruck01Icon,
  DiscountTag01Icon,
  Invoice03Icon,
  LegalDocument01Icon,
  Megaphone02Icon,
  PackageIcon,
  QrCodeIcon,
  RupeeIcon,
  Settings02Icon,
  SlidersHorizontalIcon,
  Store01Icon,
  Task01Icon,
  UserMultiple02Icon,
} from "@hugeicons/core-free-icons";
import type { Route } from "next";

import type { IconGlyph } from "@/components/ui/icon";
import { can, canApprove, type ModuleCode, type ModulePermission } from "@/lib/auth/permissions";
import type { DataId } from "@/lib/data-ids";

export interface NavItem {
  readonly id: string;
  readonly label: string;
  /** One line under the title in the top bar, on this item's own page. */
  readonly description?: string;
  readonly icon: IconGlyph;
  /** Shown when the user may view this backend module. Null: shown to everyone signed in. */
  readonly module: ModuleCode | null;
  readonly dataId: DataId;
  /** Built modules have a route. Planned modules are listed (as "Soon") but are not links. */
  readonly href?: Route;
  /** Who the item is for. "staff" hides it from partner users, whatever their permissions. */
  readonly audience?: "staff";
  /** "approvers": shown to whoever may approve an order or a quotation discount, whatever `module` says. */
  readonly visibleTo?: "approvers";
  /** A live count shown next to the label. */
  readonly countSource?: "leads" | "messages" | "approvals";
}

export interface NavSection {
  readonly id: string;
  readonly label: string;
  readonly items: readonly NavItem[];
}

/**
 * The whole application map in one place. Order matters: moving down the
 * list animates pages forward, moving up animates them back.
 *
 * Who sees what comes from the permission list in GET /auth/me (AUTH-002), so a
 * change to a role's access is made in the backend, never here.
 */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    id: "overview",
    label: "Overview",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        description: "Your territory at a glance.",
        icon: DashboardSquare02Icon,
        module: null,
        dataId: "RPT-001",
        href: "/dashboard",
      },
      {
        id: "messages",
        label: "Messages",
        description: "Talk to colleagues about a lead, an order or anything else.",
        icon: BubbleChatIcon,
        module: null,
        audience: "staff",
        dataId: "MSG-001",
        href: "/messages",
        countSource: "messages",
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
        description: "Every enquiry from WhatsApp, the website, QR codes and field staff.",
        icon: UserMultiple02Icon,
        module: "leads",
        dataId: "LEAD-001",
        href: "/leads",
        countSource: "leads",
      },
      {
        id: "quotations",
        label: "Quotations",
        description: "Quote from a lead with type-based templates, versions and approvals.",
        icon: Invoice03Icon,
        module: "quotations",
        dataId: "QUOT-001",
        href: "/quotations",
      },
      {
        id: "sales-orders",
        label: "Sales orders",
        description:
          "Orders from won leads or placed directly, with dispatch details and payment terms.",
        icon: PackageIcon,
        module: "sales_orders",
        dataId: "SO-001",
        href: "/sales-orders",
      },
      {
        id: "qr-codes",
        label: "QR codes",
        description: "Codes for printed material that open the enquiry form.",
        icon: QrCodeIcon,
        module: "leads",
        audience: "staff",
        dataId: "LEAD-013",
        href: "/qr-codes",
      },
      {
        id: "approvals",
        label: "Approvals",
        description: "Quotation discounts and sales orders waiting for your decision.",
        icon: CheckmarkBadge01Icon,
        module: "sales_orders",
        visibleTo: "approvers",
        dataId: "APPR-001",
        href: "/approvals",
        countSource: "approvals",
      },
      {
        id: "subsidy",
        label: "Subsidy",
        icon: LegalDocument01Icon,
        module: "subsidy",
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
        description: "From the farmer's report to the manager's check, QC and the remedy.",
        icon: CustomerSupportIcon,
        module: "complaints",
        dataId: "CMPL-001",
        href: "/complaints",
      },
      {
        id: "tasks",
        label: "Tasks",
        description: "Your calls, visits and meetings for the day, and your team's.",
        icon: Task01Icon,
        module: "tasks",
        audience: "staff",
        dataId: "TASK-001",
        href: "/tasks",
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
        module: "partners",
        dataId: "CHNL-001",
      },
      {
        id: "marketing",
        label: "Marketing",
        icon: Megaphone02Icon,
        module: "marketing",
        dataId: "MKT-001",
      },
      {
        id: "schemes",
        label: "Schemes",
        icon: DiscountTag01Icon,
        module: "schemes",
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
        module: "accounts",
        dataId: "ACCT-001",
      },
      {
        id: "dispatch",
        label: "Dispatch queue",
        description: "Approved orders waiting to ship, and what has left.",
        icon: DeliveryTruck01Icon,
        module: "dispatch",
        audience: "staff",
        dataId: "DISP-001",
        href: "/dispatch",
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
        module: "reports",
        dataId: "RPT-002",
      },
      {
        id: "approval-limits",
        label: "Approval limits",
        description: "How much each role may approve: an order's value and a quotation's discount.",
        icon: SlidersHorizontalIcon,
        module: "masters",
        dataId: "APPR-002",
        href: "/approval-limits",
      },
      {
        id: "complaint-targets",
        label: "Complaint targets",
        description: "How quickly a complaint is answered and resolved, by severity.",
        icon: Clock01Icon,
        module: "complaints",
        audience: "staff",
        dataId: "CMPL-008",
        href: "/complaint-targets",
      },
      {
        id: "masters",
        label: "Masters",
        icon: Database01Icon,
        module: "masters",
        dataId: "MSTR-001",
      },
      {
        id: "users",
        label: "Users & roles",
        icon: Settings02Icon,
        module: "users",
        dataId: "ADMN-001",
      },
    ],
  },
];

/**
 * `userType` is the session's `userType` ("staff", "partner_user" …). Unknown (null), it
 * hides staff-only items rather than risk showing them to a partner.
 */
export function canSeeNavItem(
  item: NavItem,
  permissions: readonly ModulePermission[],
  userType: string | null = null,
): boolean {
  if (item.audience === "staff" && userType !== "staff") {
    return false;
  }
  if (item.visibleTo === "approvers") {
    return canApprove(permissions);
  }
  return item.module === null || can(permissions, item.module, "view");
}

/** Sections and items the user may see; empty sections are dropped. */
export function visibleNavSections(
  permissions: readonly ModulePermission[],
  userType: string | null = null,
): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canSeeNavItem(item, permissions, userType)),
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

export interface PageHeading {
  readonly title: string;
  readonly description?: string;
}

/**
 * The top bar's title for a path: the section's label, with its description only on
 * the section's own page — a detail page beneath it (a lead) names itself in the content.
 */
export function findPageHeading(pathname: string): PageHeading {
  const item = findActiveNavItem(pathname);
  if (item === undefined) {
    return { title: "Polysil CRM" };
  }
  if (item.href === pathname && item.description !== undefined) {
    return { title: item.label, description: item.description };
  }
  return { title: item.label };
}
