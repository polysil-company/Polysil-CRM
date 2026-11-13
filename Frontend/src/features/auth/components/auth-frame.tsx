import type * as React from "react";

import { BrandLogo } from "@/components/patterns/brand-mark";
import { SarthiChariot, SarthiVision } from "@/components/patterns/sarthi-vision";
import { APP_NAME, APP_TAGLINE } from "@/lib/brand";

import { DripField } from "./drip-field";

/**
 * The frame of the sign-in screens: the form alone on a phone, with a brand panel beside it on
 * wide screens. The forced password change (AUTH-007) uses it too, since the app behind it
 * can't be used yet.
 *
 * APP-013 · The software is "Polysil Sarthi · Your Digital Business Partner", and the sign-in
 * screen carries the client's vision: the chariot and "To Be The Sa₹thi of Farmer's Success".
 * Phones get it as a short card under the form; wide screens as the brand panel.
 */
export function AuthFrame({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="grid min-h-dvh bg-background lg:grid-cols-2">
      <main className="flex min-w-0 flex-col px-4 py-6 sm:px-10 sm:py-8">
        <div className="flex items-center gap-3">
          <BrandLogo className="h-11" priority />
          <p className="flex min-w-0 flex-col border-l border-border pl-3">
            <span className="text-xs font-semibold tracking-wider text-foreground uppercase">
              {APP_NAME}
            </span>
            <span className="text-2xs text-muted-foreground">{APP_TAGLINE}</span>
          </p>
        </div>
        <div className="flex flex-1 items-center justify-center py-10">{children}</div>
        <section
          aria-label="Our vision"
          className="mb-4 flex items-center gap-3 rounded-xl border border-border bg-card p-3 lg:hidden"
        >
          <SarthiChariot className="size-14" />
          <SarthiVision />
        </section>
        <p className="text-xs text-subtle-foreground">Polysil Irrigation · Vadodara, Gujarat</p>
      </main>

      <aside
        aria-label={`About ${APP_NAME}`}
        className="relative m-3 hidden overflow-hidden rounded-2xl bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-end"
      >
        <DripField className="absolute inset-0" />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-3/4 bg-linear-to-t from-primary via-primary/90 to-transparent"
        />
        <div className="relative flex flex-col gap-8 p-10">
          <SarthiChariot
            priority
            className="size-40 shadow-lg ring-4 ring-primary-foreground/30 xl:size-48"
          />
          <div className="flex flex-col gap-2">
            <p className="text-2xs font-medium tracking-wider text-primary-foreground uppercase">
              Polysil Irrigation
            </p>
            <p className="text-4xl font-semibold tracking-tight uppercase">{APP_NAME}</p>
            <p className="text-lg text-primary-foreground/85">{APP_TAGLINE}</p>
          </div>
          <SarthiVision
            tone="primary"
            className="max-w-md border-l-4 border-primary-foreground/40 pl-4"
          />
        </div>
      </aside>
    </div>
  );
}
