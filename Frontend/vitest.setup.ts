import "@testing-library/jest-dom/vitest";
import "@/test/polyfills";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { removeConsoleTransport } from "@/lib/logger";
import { server } from "@/mocks/node";

// Tests assert behaviour, not console output. A test that needs log records
// registers a capture transport with registerLogTransport().
removeConsoleTransport();

beforeAll(() => {
  // Any request without a handler fails the test — no silent real network calls.
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  window.localStorage.clear();
});

afterAll(() => {
  server.close();
});
