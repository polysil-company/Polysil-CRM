"use client";

import { Search01Icon } from "@hugeicons/core-free-icons";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { NotificationBell } from "@/features/notifications/components/notification-bell";
import { cn } from "@/lib/utils";

import { useCommandMenu } from "./command-menu-context";
import { MobileNav } from "./mobile-nav";
import { findPageHeading } from "./navigation";
import { SidebarToggle } from "./sidebar-toggle";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

/**
 * The top bar: menu (phones) or sidebar toggle (desktop), the page title — the page's
 * one `h1` — with its description, then search, theme and account. Pages never repeat
 * the title (APP-005).
 */
export function AppHeader({ className }: { className?: string }): React.JSX.Element {
  const pathname = usePathname();
  const { open } = useCommandMenu();
  const heading = findPageHeading(pathname);

  return (
    <header
      className={cn(
        "flex h-header shrink-0 items-center gap-2 border-b border-border bg-panel px-3 sm:px-4 lg:gap-3 lg:px-6",
        className,
      )}
    >
      <MobileNav />
      <SidebarToggle />
      <div className="flex min-w-0 flex-col">
        <h1 className="truncate text-lg font-semibold text-foreground">{heading.title}</h1>
        {heading.description === undefined ? null : (
          <p className="hidden truncate text-sm text-muted-foreground sm:block">
            {heading.description}
          </p>
        )}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon-md"
          className="lg:hidden"
          aria-label="Search pages and actions"
          onClick={open}
        >
          <Icon icon={Search01Icon} />
        </Button>
        <NotificationBell />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
