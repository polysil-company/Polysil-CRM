import { approvalHandlers } from "./approvals";
import { authHandlers } from "./auth";
import { dashboardHandlers } from "./dashboard";
import { leadHandlers } from "./leads";
import { lookupHandlers } from "./lookups";
import { messageHandlers } from "./messages";
import { notificationHandlers } from "./notifications";
import { orderHandlers } from "./orders";
import { quotationHandlers } from "./quotations";

/**
 * What the backend does not serve yet, so it stays mocked even against a real API
 * (NEXT_PUBLIC_API_MOCKING=partial). Remove a module from this list the moment its
 * screens are connected — everything not listed goes to the real backend.
 */
export const unbuiltHandlers = [
  // TODO(NOTIF-001): served since backend #31 (BE-009); the screens are not connected yet.
  ...notificationHandlers,
  // TODO(MSG-001): served since backend #31 (BE-010); the screens are not connected yet.
  ...messageHandlers,
];

/**
 * Every mock endpoint: the full mock backend (NEXT_PUBLIC_API_MOCKING=enabled) and the
 * unit tests. A new API integration adds its handlers here first. Leads, lookups,
 * quotations, orders, approvals and the dashboard are served by the backend, so in partial mode they go to the real API.
 */
export const handlers = [
  ...authHandlers,
  ...approvalHandlers,
  ...leadHandlers,
  ...lookupHandlers,
  ...quotationHandlers,
  ...orderHandlers,
  ...dashboardHandlers,
  ...unbuiltHandlers,
];
