import { setupWorker } from "msw/browser";

import { handlers } from "./handlers";

/** Browser mock backend. Started by MockGate only when NEXT_PUBLIC_API_MOCKING=enabled. */
export const worker = setupWorker(...handlers);
