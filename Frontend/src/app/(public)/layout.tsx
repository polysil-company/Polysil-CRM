import type { Metadata } from "next";
import type * as React from "react";

import { BrandMark } from "@/components/layout/brand-mark";

export const metadata: Metadata = {
  // A customer link carries its secret in the path; never pass it on to another site.
  referrer: "no-referrer",
};

/**
 * Pages anyone may open without signing in — today the quotation link a customer is sent
 * (QUOT-012). One narrow column: they are read on a phone, from WhatsApp.
 */
export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="mx-auto flex w-full max-w-lg items-center gap-2.5 px-4 py-5 sm:px-6">
        <BrandMark className="size-8" />
        <span className="text-sm font-semibold text-foreground">Polysil Irrigation</span>
      </header>
      <main className="mx-auto w-full max-w-lg flex-1 px-4 pb-10 sm:px-6">{children}</main>
      <footer className="px-4 py-6 text-center text-xs text-subtle-foreground">
        Polysil Irrigation Systems · Vadodara, Gujarat
      </footer>
    </div>
  );
}
