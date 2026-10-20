import type * as React from "react";

import { AppShell } from "@/components/layout/app-shell";
import { FarmersToPortal } from "@/components/layout/farmers-to-portal";
import { AuthGate } from "@/features/auth/components/auth-gate";

/** Every signed-in page. proxy.ts redirects signed-out visitors before this renders. */
export default function AppLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <AuthGate>
      <FarmersToPortal>
        <AppShell>{children}</AppShell>
      </FarmersToPortal>
    </AuthGate>
  );
}
