import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke tests against the app with the mocked API (MSW).
 *
 *   npx playwright install chromium   once per machine
 *   npm run test:e2e                   starts the app, runs e2e/, writes playwright-report/
 *
 * Locally the dev server is reused if it is already running. In CI the app is
 * built and started in production mode. Set PLAYWRIGHT_BASE_URL to test a
 * deployed feature preview instead.
 */

const isCI = process.env.CI !== undefined;
const port = Number(process.env.PORT ?? "3000");
const externalBaseUrl = process.env.PLAYWRIGHT_BASE_URL;
const baseURL = externalBaseUrl ?? `http://localhost:${port}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  ...(isCI ? { workers: 1 } : {}),
  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  ...(externalBaseUrl === undefined
    ? {
        webServer: {
          command: isCI ? "npm run build && npm run start" : "npm run dev",
          url: baseURL,
          reuseExistingServer: !isCI,
          timeout: 180_000,
        },
      }
    : {}),
});
