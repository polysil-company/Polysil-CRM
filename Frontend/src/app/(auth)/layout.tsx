import type * as React from "react";

import { BrandMark } from "@/components/layout/brand-mark";
import { DripField } from "@/features/auth/components/drip-field";

/**
 * Pages for signed-out visitors. Phones get the form alone; wide screens add a
 * brand panel beside it.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="grid min-h-dvh bg-background lg:grid-cols-2">
      <main className="flex min-w-0 flex-col px-4 py-6 sm:px-10 sm:py-8">
        <div className="flex items-center gap-2.5">
          <BrandMark className="size-8" />
          <div className="flex min-w-0 flex-col">
            <span className="text-sm font-semibold text-foreground">Polysil</span>
            <span className="text-xs text-muted-foreground">CRM & DMS</span>
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center py-10">{children}</div>
        <p className="text-xs text-subtle-foreground">Polysil Irrigation · Vadodara, Gujarat</p>
      </main>

      <aside
        aria-label="About Polysil CRM"
        className="relative m-3 hidden overflow-hidden rounded-2xl bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-end"
      >
        <DripField className="absolute inset-0" />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-2/3 bg-linear-to-t from-primary via-primary/85 to-transparent"
        />
        <div className="relative flex flex-col gap-3 p-10">
          <p className="text-2xs font-medium tracking-wider text-primary-foreground/80 uppercase">
            Polysil Irrigation
          </p>
          <p className="max-w-md text-3xl font-semibold text-balance">
            From the field to head office — every lead, order and subsidy case in one place.
          </p>
        </div>
      </aside>
    </div>
  );
}
