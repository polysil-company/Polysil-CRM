import type { HttpHandler } from "msw";

import { approvalHandlers } from "./approvals";
import { authHandlers } from "./auth";
import { complaintHandlers } from "./complaints";
import { dashboardHandlers } from "./dashboard";
import { leadCaptureHandlers } from "./lead-capture";
import { leadHandlers } from "./leads";
import { lookupHandlers } from "./lookups";
import { messageHandlers } from "./messages";
import { notificationHandlers } from "./notifications";
import { orderHandlers } from "./orders";
import { quotationHandlers } from "./quotations";
import { subsidyHandlers } from "./subsidy";
import { subsidyApplicationHandlers } from "./subsidy-applications";
import { taskHandlers } from "./tasks";

/**
 * What the backend does not serve yet, so it stays mocked even against a real API
 * (NEXT_PUBLIC_API_MOCKING=partial). A module built before its endpoints exist goes here;
 * remove it the moment its screens are connected. Empty since notifications and messages
 * were connected: every screen talks to the real backend in partial mode.
 */
export const unbuiltHandlers: readonly HttpHandler[] = [];

/**
 * Every mock endpoint: the full mock backend (NEXT_PUBLIC_API_MOCKING=enabled) and the
 * unit tests. A new API integration adds its handlers here first. Everything here is served
 * by the backend, so in partial mode it goes to the real API.
 */
export const handlers: readonly HttpHandler[] = [
  ...authHandlers,
  ...approvalHandlers,
  ...leadHandlers,
  ...leadCaptureHandlers,
  ...lookupHandlers,
  ...quotationHandlers,
  ...orderHandlers,
  ...dashboardHandlers,
  ...notificationHandlers,
  ...messageHandlers,
  ...taskHandlers,
  ...complaintHandlers,
  ...subsidyHandlers,
  ...subsidyApplicationHandlers,
  ...unbuiltHandlers,
];
