import type { Route } from "next";
import type { useRouter } from "next/navigation";

import type { AssistantScreen, RecordKind } from "@/features/assistant/api/assistant.schemas";

/**
 * BOT-001 · The backend's screen keys onto this app's routes. A detail screen without a record
 * opens its list; a "new" screen without its own route opens the page whose button starts it.
 */
export function routeFor(screen: AssistantScreen): Route {
  switch (screen) {
    case "leads.new":
      return "/leads?newLead=true";
    case "leads.list":
      return "/leads";
    case "leads.detail":
      return "/leads";
    case "leads.duplicates":
      return "/leads/duplicates";
    case "leads.qr_codes":
      return "/qr-codes";
    case "customers.list":
      return "/customers";
    case "customers.detail":
      return "/customers";
    case "campaigns.list":
    case "campaigns.new":
      return "/campaigns";
    case "quotations.new":
      return "/quotations/new";
    case "quotations.list":
      return "/quotations";
    case "quotations.detail":
      return "/quotations";
    case "approvals.queue":
      return "/approvals";
    case "orders.new":
      return "/sales-orders/new";
    case "orders.list":
      return "/sales-orders";
    case "orders.detail":
      return "/sales-orders";
    case "dispatch.list":
      return "/dispatch";
    case "payments.new":
    case "payments.list":
      return "/receipts";
    case "complaints.new":
      return "/complaints/new";
    case "complaints.list":
      return "/complaints";
    case "complaints.detail":
      return "/complaints";
    case "tasks.new":
    case "tasks.planner":
      return "/tasks";
    case "subsidy.applications":
      return "/subsidy";
    case "subsidy.applications.new":
      return "/subsidy/new";
    case "schemes.list":
      return "/schemes";
    case "rewards.list":
      return "/rewards";
    case "marketing.orders.new":
      return "/marketing";
    case "stock.list":
      return "/stock";
    case "targets.list":
      return "/targets";
    case "reports.list":
      return "/reports";
    case "tracking.map":
      return "/team-map";
    case "messages.list":
      return "/messages";
    case "partners.list":
      return "/partners";
    case "users.list":
      return "/users";
    case "users.new":
      return "/users/new";
    case "products.list":
      return "/products";
    case "pricing.lists":
      return "/products?tab=price-lists";
    case "settings.holidays":
      return "/masters?tab=holidays";
    case "settings.company":
      return "/settings";
    case "settings.lookups":
      return "/masters";
  }
}

type Navigate = Pick<ReturnType<typeof useRouter>, "push">;

/** BOT-001 · Opens a found record on its own page; any other screen through `routeFor`. */
export function openScreen(router: Navigate, screen: AssistantScreen, id?: string): void {
  if (id !== undefined) {
    const ref = encodeURIComponent(id);
    switch (screen) {
      case "leads.detail":
        router.push(`/leads/${ref}`);
        return;
      case "customers.detail":
        router.push(`/customers/${ref}`);
        return;
      case "quotations.detail":
        router.push(`/quotations/${ref}`);
        return;
      case "orders.detail":
        router.push(`/sales-orders/${ref}`);
        return;
      case "complaints.detail":
        router.push(`/complaints/${ref}`);
        return;
      default:
        break;
    }
  }
  router.push(routeFor(screen));
}

export const RECORD_KIND_LABELS: Readonly<Record<RecordKind, string>> = {
  lead: "Lead",
  customer: "Customer",
  quotation: "Quotation",
  sales_order: "Sales order",
  complaint: "Complaint",
};
