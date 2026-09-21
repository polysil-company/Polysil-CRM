import type * as React from "react";

import { AppShell } from "@/components/layout/app-shell";

// TODO(AUTH-001): redirect signed-out users to sign-in (proxy.ts) once the auth contract is agreed.
export default function AppLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <AppShell>{children}</AppShell>;
}
