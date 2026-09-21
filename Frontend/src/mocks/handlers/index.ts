import { dashboardHandlers } from "./dashboard";
import { leadHandlers } from "./leads";
import { sessionHandlers } from "./session";

/** Every mock endpoint. A new API integration adds its handlers here first. */
export const handlers = [...sessionHandlers, ...leadHandlers, ...dashboardHandlers];
