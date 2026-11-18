import type {
  AssistantActionWire,
  AssistantScreen,
} from "@/features/assistant/api/assistant.schemas";
import type { ModuleCode, PermissionAction } from "@/lib/auth/permissions";

/** One action and the grant it needs; `null` is open to every staff or dealer user. */
export interface MockAssistantAction extends AssistantActionWire {
  readonly screen: AssistantScreen;
  readonly needs: { readonly module: ModuleCode; readonly action: PermissionAction } | null;
  /** Hidden from dealers and distributors, whatever their grants. */
  readonly staffOnly?: boolean;
}

function action(
  key: string,
  title: string,
  hint: string,
  screen: AssistantScreen,
  needs: MockAssistantAction["needs"],
  staffOnly = false,
): MockAssistantAction {
  return { key, title, hint, screen, module: needs?.module ?? "general", needs, staffOnly };
}

/** BOT-001, BOT-002 · A stand-in for the backend's action catalogue, most used first. */
export const MOCK_ASSISTANT_ACTIONS: readonly MockAssistantAction[] = [
  action("lead.create", "New lead", "Capture a farmer's enquiry", "leads.new", {
    module: "leads",
    action: "create",
  }),
  action("quotation.create", "New quotation", "Start from a qualified lead", "quotations.new", {
    module: "quotations",
    action: "create",
  }),
  action("task.create", "New task", "Plan a visit or a call", "tasks.new", {
    module: "tasks",
    action: "create",
  }),
  action("complaint.create", "Raise a complaint", "For a farmer or a dealer", "complaints.new", {
    module: "complaints",
    action: "create",
  }),
  action("order.create", "New sales order", "Without a quotation", "orders.new", {
    module: "sales_orders",
    action: "create",
  }),
  action("payment.record", "Record a payment", "Money received against an order", "payments.new", {
    module: "payments",
    action: "create",
  }),
  action("approval.queue", "Approvals", "Orders and discounts waiting on you", "approvals.queue", {
    module: "sales_orders",
    action: "approve",
  }),
  action("lead.list", "Leads", "Every lead you can see", "leads.list", {
    module: "leads",
    action: "view",
  }),
  action("lead.duplicates", "Possible duplicate leads", "Review and merge", "leads.duplicates", {
    module: "leads",
    action: "edit",
  }),
  action("lead.qr_codes", "QR codes", "Enquiry codes for posters and stalls", "leads.qr_codes", {
    module: "leads",
    action: "create",
  }),
  action("customer.list", "Customers", "Farmers and institutions who bought", "customers.list", {
    module: "leads",
    action: "view",
  }),
  action("campaign.list", "Campaigns", "Campaigns and their leads", "campaigns.list", {
    module: "campaigns",
    action: "view",
  }),
  action("campaign.create", "New campaign", "Plan a campaign", "campaigns.new", {
    module: "campaigns",
    action: "create",
  }),
  action("quotation.list", "Quotations", "Drafts, sent and accepted", "quotations.list", {
    module: "quotations",
    action: "view",
  }),
  action("order.list", "Sales orders", "Every order you can see", "orders.list", {
    module: "sales_orders",
    action: "view",
  }),
  action("dispatch.list", "Dispatch", "Orders ready to send", "dispatch.list", {
    module: "dispatch",
    action: "view",
  }),
  action("payment.list", "Payments", "Receipts and dealer ledgers", "payments.list", {
    module: "payments",
    action: "view",
  }),
  action("complaint.list", "Complaints", "Open complaints and their deadlines", "complaints.list", {
    module: "complaints",
    action: "view",
  }),
  action("task.planner", "Tasks and planner", "Today's work and the week ahead", "tasks.planner", {
    module: "tasks",
    action: "view",
  }),
  action(
    "subsidy.applications",
    "Subsidy applications",
    "Files with the state agencies",
    "subsidy.applications",
    { module: "subsidy", action: "view" },
  ),
  action(
    "subsidy.apply",
    "New subsidy application",
    "For a farmer's quotation",
    "subsidy.applications.new",
    { module: "subsidy", action: "create" },
  ),
  action("scheme.list", "Schemes", "Dealer schemes and their benefits", "schemes.list", {
    module: "schemes",
    action: "view",
  }),
  action("reward.list", "Reward points", "Points earned and redeemed", "rewards.list", {
    module: "rewards",
    action: "view",
  }),
  action(
    "marketing.order",
    "Order marketing material",
    "Banners, leaflets and samples",
    "marketing.orders.new",
    { module: "marketing_material", action: "create" },
  ),
  action("stock.list", "Stock", "What is in each warehouse", "stock.list", {
    module: "stock",
    action: "view",
  }),
  action("target.list", "Targets", "Targets and how far along they are", "targets.list", {
    module: "targets",
    action: "view",
  }),
  action("report.list", "Reports", "Sales, leads, subsidy and more", "reports.list", {
    module: "reports",
    action: "view",
  }),
  action("tracking.map", "Team map", "Where the field team is today", "tracking.map", {
    module: "tracking",
    action: "view",
  }),
  action("message.list", "Messages", "Conversations and groups", "messages.list", null, true),
  action("partner.list", "Dealers and distributors", "Partners and applications", "partners.list", {
    module: "partners",
    action: "view",
  }),
  action("user.list", "Users and roles", "Who signs in, with what role", "users.list", {
    module: "users",
    action: "view",
  }),
  action("user.create", "Add a user", "A staff or partner user", "users.new", {
    module: "users",
    action: "create",
  }),
  action("product.list", "Products", "The catalogue, HSN and tax", "products.list", {
    module: "products",
    action: "view",
  }),
  action("pricing.lists", "Price lists", "Prices by list and date", "pricing.lists", {
    module: "pricing",
    action: "view",
  }),
  action("settings.holidays", "Holidays", "Days off, for deadlines", "settings.holidays", {
    module: "masters",
    action: "edit",
  }),
  action(
    "settings.company",
    "Company settings",
    "Rules for orders and complaints",
    "settings.company",
    {
      module: "masters",
      action: "edit",
    },
    true,
  ),
  action(
    "settings.lookups",
    "Lists and masters",
    "Sources, offices, territories",
    "settings.lookups",
    {
      module: "masters",
      action: "view",
    },
  ),
];
