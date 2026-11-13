import "./globals.css";

import type { Metadata, Viewport } from "next";
import type * as React from "react";

import { AppProviders } from "@/components/providers/app-providers";
import { InlineScript } from "@/components/ui/inline-script";
import { APP_NAME, APP_TAGLINE } from "@/lib/brand";
import { clientEnv } from "@/lib/env/client";
import { SIDEBAR_INIT_SCRIPT } from "@/lib/sidebar/sidebar";
import { THEME_INIT_SCRIPT } from "@/lib/theme/theme";
import { cn } from "@/lib/utils";

import { fontVariables } from "./fonts";

export const metadata: Metadata = {
  // APP-013 · The software's name, from the client (13 Nov 2026).
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: `${APP_NAME}, ${APP_TAGLINE.toLowerCase()}: Polysil Irrigation's CRM and dealer management.`,
  applicationName: APP_NAME,
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Browser UI colour. Keep in sync with --background in src/styles/tokens.css.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f3f0" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0d10" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <html
      lang="en-IN"
      suppressHydrationWarning
      data-app-env={clientEnv.appEnv}
      className={cn(fontVariables, "h-full")}
    >
      <head>
        {/* Applies the saved theme before first paint, so the page never flashes the wrong one. */}
        <InlineScript html={THEME_INIT_SCRIPT} />
        {/* Applies the saved sidebar width the same way, so a collapsed sidebar never flashes open. */}
        <InlineScript html={SIDEBAR_INIT_SCRIPT} />
      </head>
      <body className="min-h-full">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
