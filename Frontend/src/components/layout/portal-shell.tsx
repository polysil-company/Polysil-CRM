"use client";

import { Logout01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { BrandMark } from "@/components/patterns/brand-mark";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useSignOut } from "@/features/auth/hooks/use-sign-out";
import { useSession } from "@/features/session/hooks/use-session";

import { ThemeToggle } from "./theme-toggle";

/**
 * FARM-001 · The farmers' portal frame: a simple header with the brand, the theme and Sign out,
 * and one narrow column. No sidebar, no search: a farmer comes here to look up their own record.
 * Staff and dealers who open it are pointed back to the main app.
 */
export function PortalShell({ children }: { children: React.ReactNode }): React.JSX.Element {
  const session = useSession();
  const { signOut, isSigningOut } = useSignOut();
  const consumer = session.data?.userType === "consumer";

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="sticky top-0 layer-sticky border-b border-border bg-background/90 backdrop-blur-sm">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between gap-3 px-4">
          <div className="flex min-w-0 items-center gap-2">
            <BrandMark className="size-7" />
            <div className="flex min-w-0 flex-col leading-tight">
              <span className="text-sm font-semibold text-foreground">Polysil</span>
              <span className="truncate text-xs text-muted-foreground">Your irrigation record</span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <Button
              variant="ghost"
              size="sm"
              state={isSigningOut ? "loading" : "idle"}
              loadingLabel="Signing out…"
              onClick={() => {
                void signOut();
              }}
            >
              <Icon icon={Logout01Icon} />
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-6 sm:py-8">
        {session.status === "pending" ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : session.status === "success" && !consumer ? (
          <NotForStaff />
        ) : (
          children
        )}
      </main>
    </div>
  );
}

/** Staff and dealers get `not_a_consumer` on every portal call: say so before they try. */
function NotForStaff(): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="flex-col gap-1">
        <h1 className="text-lg font-semibold text-foreground">This is the farmers&apos; portal</h1>
        <CardDescription>
          Farmers sign in here with their mobile to see their own record. Staff and dealers work in
          the main app.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Link
          href="/dashboard"
          className="text-sm font-medium text-primary-text underline-offset-4 hover:underline"
        >
          Go to the main app
        </Link>
      </CardContent>
    </Card>
  );
}
