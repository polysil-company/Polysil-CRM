"use client";

import { usePathname } from "next/navigation";
import type * as React from "react";

import { AccessDenied } from "@/components/patterns/access-denied";
import { PageContainer } from "@/components/patterns/page-container";
import { useSession } from "@/features/session/hooks/use-session";

import { canOpenPath } from "./navigation";

/**
 * APP-006 · Renders the page only when the user may open it. Otherwise the whole page is
 * replaced by "You don't have access", so no header, filter or skeleton is drawn behind it
 * (walk F-8, F-17). The session is loaded before the shell renders (AuthGate); if it could
 * not be read, the page renders and the backend's 403 decides.
 */
export function RouteGuard({ children }: { children: React.ReactNode }): React.JSX.Element {
  const pathname = usePathname();
  const { data: session } = useSession();

  if (session !== undefined && !canOpenPath(pathname, session.permissions, session.userType)) {
    return (
      <PageContainer className="min-h-full justify-center">
        <AccessDenied />
      </PageContainer>
    );
  }
  return <>{children}</>;
}
