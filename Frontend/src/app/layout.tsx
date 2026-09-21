import "./globals.css";

import type { Metadata, Viewport } from "next";
import type * as React from "react";

import { AppProviders } from "@/components/providers/app-providers";
import { clientEnv } from "@/lib/env/client";
import { THEME_INIT_SCRIPT } from "@/lib/theme/theme";
import { cn } from "@/lib/utils";

import { fontVariables } from "./fonts";

export const metadata: Metadata = {
  title: { default: "Polysil CRM", template: "%s · Polysil CRM" },
  description: "Polysil Irrigation — CRM and dealer management.",
  applicationName: "Polysil CRM",
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
        <script
          // eslint-disable-next-line react/no-danger -- Must run before first paint to avoid a theme flash; the content is a constant from src/lib/theme/theme.ts.
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
      </head>
      <body className="min-h-full">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
