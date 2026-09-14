"use client";

import { Search01Icon } from "@hugeicons/core-free-icons";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

import { useCommandMenu } from "./command-menu-context";
import { MobileNav } from "./mobile-nav";
import { findActiveNavItem } from "./navigation";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

export function AppHeader({ className }: { className?: string }): React.JSX.Element {
  const pathname = usePathname();
  const { open } = useCommandMenu();
  const current = findActiveNavItem(pathname);

  return (
    <header
      className={cn(
        "flex h-header shrink-0 items-center gap-2 border-b border-border bg-panel px-3 sm:px-4 lg:px-6",
        className,
      )}
    >
      <MobileNav />
      <p className="min-w-0 truncate text-sm font-medium text-foreground">
        {current?.label ?? "Polysil CRM"}
      </p>
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-md"
          className="lg:hidden"
          aria-label="Search pages and actions"
          onClick={open}
        >
          <Icon icon={Search01Icon} />
        </Button>
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
