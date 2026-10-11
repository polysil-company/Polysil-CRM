import type * as React from "react";

import { AuthFrame } from "@/features/auth/components/auth-frame";

/**
 * Pages for signed-out visitors. Phones get the form alone; wide screens add a
 * brand panel beside it.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <AuthFrame>{children}</AuthFrame>;
}
