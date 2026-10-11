import { setupWorker } from "msw/browser";

import { clientEnv } from "@/lib/env/client";

import { handlers, unbuiltHandlers } from "./handlers";

/**
 * Browser mock backend, started by MockGate. In `partial` mode it answers only what the
 * backend does not serve yet; MockGate starts it with `onUnhandledRequest: "bypass"`, so
 * every other request goes on to the real API.
 */
export const worker = setupWorker(
  ...(clientEnv.apiMocking === "partial" ? unbuiltHandlers : handlers),
);
