import { authHandlers } from "./auth";
import { dashboardHandlers } from "./dashboard";
import { leadHandlers } from "./leads";
import { messageHandlers } from "./messages";
import { notificationHandlers } from "./notifications";

/** Every mock endpoint. A new API integration adds its handlers here first. */
export const handlers = [
  ...authHandlers,
  ...leadHandlers,
  ...dashboardHandlers,
  ...notificationHandlers,
  ...messageHandlers,
];
