import type { HttpHandler } from "msw";

import { approvalHandlers } from "./approvals";
import { authHandlers } from "./auth";
import { campaignHandlers } from "./campaigns";
import { commissionHandlers } from "./commission";
import { complaintHandlers } from "./complaints";
import { customerHandlers } from "./customers";
import { dashboardHandlers } from "./dashboard";
import { dealerApplicationHandlers } from "./dealer-applications";
import { documentHandlers } from "./documents";
import { holidayHandlers } from "./holidays";
import { importHandlers } from "./imports";
import { leadCaptureHandlers } from "./lead-capture";
import { leadHandlers } from "./leads";
import { lookupHandlers } from "./lookups";
import { marketingHandlers } from "./marketing";
import { messageHandlers } from "./messages";
import { notificationHandlers } from "./notifications";
import { orderHandlers } from "./orders";
import { partnerHandlers } from "./partners";
import { paymentHandlers } from "./payments";
import { productHandlers } from "./products";
import { quotationHandlers } from "./quotations";
import { ratingHandlers } from "./ratings";
import { reportHandlers } from "./reports";
import { orderPointsHandlers, rewardHandlers } from "./rewards";
import { schemeHandlers } from "./schemes";
import { sellerGstinHandlers } from "./seller-gstins";
import { settingsHandlers } from "./settings";
import { stockHandlers } from "./stock";
import { subsidyHandlers } from "./subsidy";
import { subsidyApplicationHandlers } from "./subsidy-applications";
import { subsidyMasterHandlers } from "./subsidy-masters";
import { subsidyReportHandlers } from "./subsidy-reports";
import { subsidySchemeHandlers } from "./subsidy-schemes";
import { targetHandlers } from "./targets";
import { taskHandlers } from "./tasks";
import { territoryHandlers } from "./territories";
import { userHandlers } from "./users";
import { warrantyHandlers } from "./warranty";

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
  ...targetHandlers,
  ...complaintHandlers,
  ...userHandlers,
  ...partnerHandlers,
  ...dealerApplicationHandlers,
  ...territoryHandlers,
  ...settingsHandlers,
  ...paymentHandlers,
  ...commissionHandlers,
  ...rewardHandlers,
  ...orderPointsHandlers,
  ...marketingHandlers,
  ...campaignHandlers,
  ...stockHandlers,
  ...customerHandlers,
  ...ratingHandlers,
  ...warrantyHandlers,
  ...holidayHandlers,
  ...sellerGstinHandlers,
  ...schemeHandlers,
  ...subsidyHandlers,
  ...subsidyApplicationHandlers,
  ...subsidyReportHandlers,
  ...subsidyMasterHandlers,
  ...subsidySchemeHandlers,
  ...unbuiltHandlers,
];
