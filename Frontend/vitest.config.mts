import path from "node:path";
import { fileURLToPath } from "node:url";

import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Two test projects:
 *  - unit       jsdom + Testing Library. Fast; runs on pre-push and in CI.   `npm test`
 *  - storybook  every story rendered in real Chromium with accessibility
 *               checks. Needs `npx playwright install chromium` once.      `npm run test:storybook`
 */
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(dirname, "src") },
  },
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.stories.tsx", "src/**/*.test.{ts,tsx}", "src/mocks/**", "src/test/**"],
    },
    projects: [
      {
        extends: true,
        plugins: [react()],
        test: {
          name: "unit",
          environment: "jsdom",
          include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
          setupFiles: ["./vitest.setup.ts"],
          restoreMocks: true,
          // Tests are written for the full mock backend. Pin it, so a local .env.local
          // pointing at the dev API (NEXT_PUBLIC_API_MOCKING=partial) can't change them.
          env: { NEXT_PUBLIC_APP_ENV: "development", NEXT_PUBLIC_API_MOCKING: "enabled" },
        },
      },
      {
        extends: true,
        plugins: [
          storybookTest({
            configDir: path.join(dirname, ".storybook"),
            storybookScript: "npm run storybook -- --no-open",
          }),
        ],
        test: {
          name: "storybook",
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
});
