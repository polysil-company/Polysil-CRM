import type * as React from "react";

import { PortalShell } from "@/components/layout/portal-shell";
import { AuthGate } from "@/features/auth/components/auth-gate";

/** FARM-001 · The farmers' portal: signed in, in its own simple frame. */
export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <AuthGate>
      <PortalShell>{children}</PortalShell>
    </AuthGate>
  );
}
