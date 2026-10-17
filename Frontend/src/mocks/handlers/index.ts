import type { HttpHandler } from "msw";

import { approvalHandlers } from "./approvals";
import { authHandlers } from "./auth";
import { complaintHandlers } from "./complaints";
import { dashboardHandlers } from "./dashboard";
import { dealerApplicationHandlers } from "./dealer-applications";
import { documentHandlers } from "./documents";
import { importHandlers } from "./imports";
import { leadCaptureHandlers } from "./lead-capture";
import { leadHandlers } from "./leads";
import { lookupHandlers } from "./lookups";
import { messageHandlers } from "./messages";
import { notificationHandlers } from "./notifications";
import { orderHandlers } from "./orders";
import { partnerHandlers } from "./partners";
import { productHandlers } from "./products";
import { quotationHandlers } from "./quotations";
import { reportHandlers } from "./reports";
import { settingsHandlers } from "./settings";
import { subsidyHandlers } from "./subsidy";
import { subsidyApplicationHandlers } from "./subsidy-applications";
import { subsidyMasterHandlers } from "./subsidy-masters";
import { subsidyReportHandlers } from "./subsidy-reports";
import { subsidySchemeHandlers } from "./subsidy-schemes";
import { taskHandlers } from "./tasks";
import { territoryHandlers } from "./territories";
import { userHandlers } from "./users";

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
  ...productHandlers,
  ...importHandlers,
  ...documentHandlers,
  ...orderHandlers,
  ...dashboardHandlers,
  ...reportHandlers,
  ...notificationHandlers,
  ...messageHandlers,
  ...taskHandlers,
  ...complaintHandlers,
  ...userHandlers,
  ...partnerHandlers,
  ...dealerApplicationHandlers,
  ...territoryHandlers,
  ...settingsHandlers,
  ...subsidyHandlers,
  ...subsidyApplicationHandlers,
  ...subsidyReportHandlers,
  ...subsidyMasterHandlers,
  ...subsidySchemeHandlers,
  ...unbuiltHandlers,
];
