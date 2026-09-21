"use client";

import { useState } from "react";

import { signOut as signOutRequest } from "@/features/auth/api/auth.api";
import { endSession } from "@/lib/auth/session-store";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "features/auth/hooks/use-sign-out.ts", dataId: "AUTH-005" });

export interface SignOut {
  readonly signOut: () => Promise<void>;
  readonly isSigningOut: boolean;
}

/**
 * AUTH-005 · Signs out of this device. The session ends here even when the request
 * fails (offline): the screen must never stay signed in after the user asked to
 * leave. The session gate then clears cached data and opens the sign-in page.
 */
export function useSignOut(): SignOut {
  const [isSigningOut, setIsSigningOut] = useState(false);

  const signOut = async (): Promise<void> => {
    if (isSigningOut) {
      return;
    }
    setIsSigningOut(true);
    try {
      await log.trace("handleSignOut", () => signOutRequest(), { dataId: "AUTH-005" });
    } catch {
      // Already logged by apiRequest. The backend expires the refresh token on its own.
    } finally {
      endSession("signed-out");
      setIsSigningOut(false);
    }
  };

  return { signOut, isSigningOut };
}
