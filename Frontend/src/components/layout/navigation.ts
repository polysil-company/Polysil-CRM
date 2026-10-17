import {
  Analytics01Icon,
  BubbleChatIcon,
  CheckmarkBadge01Icon,
  Clock01Icon,
  Coins01Icon,
  CustomerSupportIcon,
  DashboardSquare02Icon,
  Database01Icon,
  DeliveryTruck01Icon,
  DiscountTag01Icon,
  GiftIcon,
  GridTableIcon,
  Invoice03Icon,
  LegalDocument01Icon,
  Megaphone02Icon,
  PackageIcon,
  PackageOpenIcon,
  QrCodeIcon,
  RupeeIcon,
  Settings02Icon,
  Settings05Icon,
  SlidersHorizontalIcon,
  Store01Icon,
  Target02Icon,
  Task01Icon,
  UserMultiple02Icon,
} from "@hugeicons/core-free-icons";
import type { Route } from "next";

import type { IconGlyph } from "@/components/ui/icon";
import { can, canApprove, type ModuleCode, type ModulePermission } from "@/lib/auth/permissions";
import type { DataId } from "@/lib/data-ids";
import { clientEnv } from "@/lib/env/client";

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
  readonly countSource?: "leads" | "messages" | "approvals" | "accounts";
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
        description: "Leads, quotations, orders and service at a glance.",
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
        description: "Applications through the scheme's stages, and the subsidy calculator.",
        icon: LegalDocument01Icon,
        module: "subsidy",
        // Portal users get 403 on every subsidy endpoint (handover subsidy-calculation.md).
        audience: "staff",
        dataId: "SUBS-005",
        href: "/subsidy",
      },
      {
        id: "targets",
        label: "Targets",
        description: "Your month against its targets, and your team's.",
        icon: Target02Icon,
        module: "targets",
        audience: "staff",
        dataId: "TGT-001",
        href: "/targets",
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
        description: "Distributors, their dealers and the dealers' sub-dealers.",
        icon: Store01Icon,
        module: "partners",
        // TODO(CHNL-002): a distributor or dealer may add the next type down from the portal
        // (partners.md); the screens are staff only until that is agreed with the client.
        audience: "staff",
        dataId: "CHNL-001",
        href: "/partners",
      },
      {
        id: "marketing",
        label: "Marketing material",
        description: "Order caps, banners and kits, with the company's and the dealer's shares.",
        icon: Megaphone02Icon,
        module: "marketing_material",
        dataId: "MKT-003",
        href: "/marketing",
      },
      {
        id: "schemes",
        label: "Schemes",
        description: "Discounts, points and credits for dealers, and the credits earned.",
        icon: DiscountTag01Icon,
        module: "schemes",
        dataId: "SCHM-001",
        href: "/schemes",
      },
      {
        id: "rewards",
        label: "Rewards",
        description: "Reward points: the balance, its history, and the gifts they buy.",
        icon: GiftIcon,
        module: "rewards",
        dataId: "RWD-001",
        href: "/rewards",
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
        description: "Submitted orders waiting on Accounts' payment check.",
        icon: RupeeIcon,
        // The backend has no `accounts` module: Accounts holds `payments` (RBAC.md §6.2).
        module: "payments",
        audience: "staff",
        dataId: "ACCT-001",
        href: "/accounts",
        countSource: "accounts",
      },
      {
        id: "dealer-commissions",
        label: "Dealer commissions",
        description: "Subsidy stage 18: commissions to approve, to pay, and paid.",
        icon: Coins01Icon,
        // Accounts approves and pays (payments); co-ordinators work from the application.
        module: "payments",
        audience: "staff",
        dataId: "SUBS-017",
        href: "/dealer-commissions",
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
        description:
          "Conversion, people, lost leads, follow-ups, dealers, campaigns, areas and complaints.",
        icon: Analytics01Icon,
        module: "reports",
        dataId: "RPT-002",
        href: "/reports",
      },
      {
        id: "approval-limits",
        label: "Approval limits",
        description: "How much each role may approve: an order's value and a quotation's discount.",
        icon: SlidersHorizontalIcon,
        module: "masters",
        // GET /approvals/thresholds is 403 for anyone who is not staff (walk F-8).
        audience: "staff",
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
        id: "subsidy-masters",
        label: "Subsidy masters",
        description: "The scheme's categories, rates, crop spacings and unit-cost tables, by date.",
        icon: GridTableIcon,
        module: "masters",
        audience: "staff",
        dataId: "SUBS-012",
        href: "/subsidy-masters",
      },
      {
        id: "products",
        label: "Products & prices",
        description: "The catalogue, its price lists and the GST rate for each HSN code.",
        icon: PackageOpenIcon,
        module: "products",
        audience: "staff",
        dataId: "MSTR-004",
        href: "/products",
      },
      {
        id: "masters",
        label: "Masters",
        description:
          "The lists every form picks from, how a lead is scored, the offices and the territories.",
        icon: Database01Icon,
        module: "masters",
        audience: "staff",
        dataId: "MSTR-001",
        href: "/masters",
      },
      {
        id: "company-settings",
        label: "Company settings",
        description: "Rules for orders, complaints, dealers and the farmers' portal.",
        icon: Settings05Icon,
        module: "masters",
        // GET /settings is staff only (settings-amend-reopen-contract.md).
        audience: "staff",
        dataId: "ADMN-007",
        href: "/settings",
      },
      {
        id: "users",
        label: "Users & roles",
        icon: Settings02Icon,
        href: "/users",
        module: "users",
        dataId: "ADMN-001",
        description: "Staff and partner users: who signs in, with what role, where.",
      },
    ],
  },
];

/**
 * `userType` is the session's `userType` ("staff", "partner_user" …). Unknown (null), it
 * hides staff-only items rather than risk showing them to a partner.
 */
/**
 * APP-007 · Whether a deployment releases this item: `NEXT_PUBLIC_NAV_ONLY` lists the nav item
 * ids a client's box shows (the deploy script's RELEASED_NAV). Null releases everything.
 */
export function isReleased(item: NavItem, navOnly: readonly string[] | null): boolean {
  return navOnly === null || navOnly.includes(item.id);
}

export function canSeeNavItem(
  item: NavItem,
  permissions: readonly ModulePermission[],
  userType: string | null = null,
  navOnly: readonly string[] | null = clientEnv.navOnly,
): boolean {
  if (!isReleased(item, navOnly)) {
    return false;
  }
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
  navOnly: readonly string[] | null = clientEnv.navOnly,
): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canSeeNavItem(item, permissions, userType, navOnly)),
  })).filter((section) => section.items.length > 0);
}

/**
 * Pages below a nav item that are for staff even when the item is not: a partner user sees
 * no possible duplicates (the backend sends none and refuses to dismiss one, walk F-1).
 */
const STAFF_ONLY_PATHS: readonly string[] = ["/leads/duplicates"];

/**
 * APP-006 · Whether the user may open a page, by the same rule that shows its nav item, so a
 * page left out of someone's menu cannot be opened by typing its address either (walk F-8).
 * Pages outside the nav map are open to everyone signed in. A courtesy: the backend enforces.
 * A screen the deployment doesn't release (APP-007) can't be opened either.
 */
export function canOpenPath(
  pathname: string,
  permissions: readonly ModulePermission[],
  userType: string | null = null,
  navOnly: readonly string[] | null = clientEnv.navOnly,
): boolean {
  const staffOnly = STAFF_ONLY_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
  if (staffOnly && userType !== "staff") {
    return false;
  }
  const item = findActiveNavItem(pathname);
  return item === undefined || canSeeNavItem(item, permissions, userType, navOnly);
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
