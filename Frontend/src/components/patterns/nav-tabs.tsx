"use client";

import { motion } from "motion/react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { formatCount } from "@/lib/format";
import { SPRING } from "@/lib/motion/tokens";
import { cn } from "@/lib/utils";

export interface NavTab {
  readonly href: Route;
  readonly label: string;
  readonly count?: number | undefined;
  /** The count is a lower bound (the API stopped counting): shown as "1,000+". */
  readonly countCapped?: boolean;
  /** Shown but not navigable (e.g. a module that is not built yet). */
  readonly disabled?: boolean;
}

export interface NavTabsProps {
  tabs: readonly NavTab[];
  /** Accessible name of the navigation, e.g. "Sales documents". */
  label: string;
  /** Unique per page so indicators on different pages never animate between each other. */
  indicatorId: string;
  className?: string;
}

/**
 * Tabs that change the URL. The underline glides to the new tab, and the page
 * slides in the direction of travel (left tab → right tab = forward).
 */
export function NavTabs({ tabs, label, indicatorId, className }: NavTabsProps): React.JSX.Element {
  const pathname = usePathname();
  // The longest matching href wins, so a tab at "/subsidy" stays off on "/subsidy/calculator".
  const activeIndex = tabs.reduce(
    (best, tab, index) =>
      (pathname === tab.href || pathname.startsWith(`${tab.href}/`)) &&
      (best === -1 || tab.href.length > (tabs[best]?.href.length ?? 0))
        ? index
        : best,
    -1,
  );

  return (
    <nav
      aria-label={label}
      className={cn(
        "relative scrollbar-none flex items-center gap-5 overflow-x-auto border-b border-border",
        className,
      )}
    >
      {tabs.map((tab, index) => {
        const active = index === activeIndex;
        const content = (
          <>
            {tab.label}
            {tab.count === undefined ? null : (
              <Badge size="sm" variant={active ? "primary" : "neutral"}>
                {formatCount(tab.count, { atLeast: tab.countCapped === true })}
              </Badge>
            )}
            {active ? (
              <motion.span
                layoutId={indicatorId}
                transition={SPRING.snappy}
                className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-foreground"
              />
            ) : null}
          </>
        );

        if (tab.disabled) {
          return (
            <span
              key={tab.href}
              aria-disabled="true"
              className="relative inline-flex h-control-md shrink-0 cursor-not-allowed items-center gap-1.5 text-sm font-medium text-subtle-foreground"
            >
              {content}
            </span>
          );
        }

        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            transitionTypes={[index > activeIndex ? "nav-forward" : "nav-back"]}
            className={cn(
              "relative inline-flex h-control-md shrink-0 items-center gap-1.5 text-sm font-medium focus-ring-inset transition-colors duration-fast",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {content}
          </Link>
        );
      })}
    </nav>
  );
}
