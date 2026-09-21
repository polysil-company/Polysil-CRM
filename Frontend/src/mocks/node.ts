import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/** Node mock backend for Vitest — same handlers as the browser. */
export const server = setupServer(...handlers);
