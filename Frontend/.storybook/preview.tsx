import "../src/app/globals.css";

import { withThemeByClassName } from "@storybook/addon-themes";
import type { Preview } from "@storybook/nextjs-vite";
import { MotionConfig } from "motion/react";

import { fontVariables } from "@/app/fonts";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const preview: Preview = {
  parameters: {
    layout: "centered",
    controls: {
      expanded: true,
      matchers: { color: /(background|color)$/i, date: /Date$/i },
    },
    // Accessibility violations fail `npm run test:storybook`.
    a11y: { test: "error" },
    nextjs: { appDirectory: true },
  },
  decorators: [
    withThemeByClassName({
      themes: { light: "", dark: "dark" },
      defaultTheme: "light",
    }),
    (Story) => (
      <MotionConfig reducedMotion="user">
        <TooltipProvider>
          <div className={cn(fontVariables, "font-sans text-foreground")}>
            <Story />
          </div>
        </TooltipProvider>
      </MotionConfig>
    ),
  ],
  tags: ["autodocs"],
};

export default preview;
