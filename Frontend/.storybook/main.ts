import type { StorybookConfig } from "@storybook/nextjs-vite";

/**
 * Storybook is the component preview and tweaking environment.
 * Every component in src/components ships a `*.stories.tsx` next to it,
 * covering all its states in light and dark.
 */
const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [
    "@storybook/addon-docs",
    "@storybook/addon-a11y",
    "@storybook/addon-themes",
    "@storybook/addon-vitest",
  ],
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
  staticDirs: ["../public"],
  core: {
    disableTelemetry: true,
  },
};

export default config;
