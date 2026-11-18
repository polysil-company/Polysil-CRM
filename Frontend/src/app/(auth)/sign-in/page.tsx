import type { Metadata } from "next";
import type * as React from "react";

import { SignInScreen } from "@/features/auth/components/sign-in-screen";
import { isSessionEndReason, safeNextPath } from "@/lib/auth/redirects";

export const metadata: Metadata = { title: "Sign in" };

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function SignInPage({
  searchParams,
}: PageProps<"/sign-in">): Promise<React.JSX.Element> {
  const params = await searchParams;
  const reason = firstValue(params.reason);

  return (
    <SignInScreen
      next={safeNextPath(firstValue(params.next))}
      reason={isSessionEndReason(reason) ? reason : null}
    />
  );
}
