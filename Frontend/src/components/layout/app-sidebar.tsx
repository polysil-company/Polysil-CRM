"use client";

import { Search01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { leadSummaryQueryOptions } from "@/features/leads/api/leads.queries";
import { useSession } from "@/features/session/hooks/use-session";
import { useModifierKeyLabel } from "@/hooks/use-modifier-key";
import { clientEnv, type AppEnv } from "@/lib/env/client";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { BrandMark } from "./brand-mark";
import { useCommandMenu } from "./command-menu-context";
import { isNavItemActive, visibleNavSections, type NavItem } from "./navigation";

const ENVIRONMENT_LABELS: Readonly<Record<AppEnv, string>> = {
  development: "Local",
  feature: "Preview",
  staging: "Staging",
  production: "Production",
};

type Navigate = (() => void) | undefined;

export function AppSidebar({ className }: { className?: string }): React.JSX.Element {
  return (
    <aside aria-label="Sidebar" className={cn("flex h-dvh flex-col bg-sidebar", className)}>
      <SidebarContent />
    </aside>
  );
}

/** Shared by the desktop sidebar and the mobile menu sheet. */
export function SidebarContent({ onNavigate }: { onNavigate?: Navigate }): React.JSX.Element {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 px-3 py-4">
      <SidebarBrand />
      <SidebarSearchButton onOpen={onNavigate} />
      <SidebarNav onNavigate={onNavigate} />
      <SidebarEnvironmentCard />
    </div>
  );
}

function SidebarBrand(): React.JSX.Element {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <BrandMark className="size-7" />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-semibold text-foreground">Polysil</span>
        <span className="truncate text-xs text-muted-foreground">CRM & DMS</span>
      </div>
      {clientEnv.appEnv === "production" ? null : (
        <Badge size="sm" variant="highlight" className="ml-auto">
          {ENVIRONMENT_LABELS[clientEnv.appEnv]}
        </Badge>
      )}
    </div>
  );
}

function SidebarSearchButton({ onOpen }: { onOpen: Navigate }): React.JSX.Element {
  const { open } = useCommandMenu();
  const modifier = useModifierKeyLabel();

  return (
    <button
      type="button"
      onClick={() => {
        onOpen?.();
        open();
      }}
      className="flex h-control-sm w-full press-scale items-center gap-2 rounded-md border border-border bg-card px-2 text-sm text-subtle-foreground shadow-xs hover:border-border-strong hover:text-muted-foreground"
    >
      <Icon icon={Search01Icon} size="sm" />
      <span className="flex-1 text-left">Find…</span>
      <KbdGroup>
        <Kbd>{modifier}</Kbd>
        <Kbd>K</Kbd>
      </KbdGroup>
    </button>
  );
}

function SidebarNav({ onNavigate }: { onNavigate: Navigate }): React.JSX.Element {
  const pathname = usePathname();
  const session = useSession();

  if (session.status === "pending") {
    return <SidebarNavSkeleton />;
  }

  if (session.status === "error") {
    return (
      <div
        role="alert"
        className="flex flex-1 flex-col items-start gap-2 px-2 text-sm text-muted-foreground"
      >
        Couldn&apos;t load your menu.
        <Button
          variant="outline"
          size="xs"
          onClick={() => {
            void session.refetch();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  const sections = visibleNavSections(session.data.role);
  const items = sections.flatMap((section) => section.items);
  const activeIndex = items.findIndex((item) => isNavItemActive(item, pathname));

  return (
    <nav aria-label="Primary" className="-mx-3 min-h-0 flex-1 scrollbar-thin overflow-y-auto px-3">
      {sections.map((section) => (
        <div key={section.id} className="mb-5 last:mb-0">
          <h2 className="px-2 pb-1.5 text-2xs font-medium tracking-wider text-subtle-foreground uppercase">
            {section.label}
          </h2>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const index = items.indexOf(item);
              return (
                <li key={item.id}>
                  <SidebarItem
                    item={item}
                    active={index === activeIndex}
                    transitionType={index > activeIndex ? "nav-forward" : "nav-back"}
                    onNavigate={onNavigate}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarItem({
  item,
  active,
  transitionType,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  transitionType: "nav-forward" | "nav-back";
  onNavigate: Navigate;
}): React.JSX.Element {
  const itemClasses =
    "group/item relative flex h-control-sm items-center gap-2.5 rounded-md px-2 text-sm font-medium";

  const content = (
    <>
      <Icon
        icon={item.icon}
        className={cn(
          "transition-colors duration-fast",
          active ? "text-foreground" : "text-subtle-foreground group-hover/item:text-foreground",
        )}
      />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      {item.href === undefined ? (
        <Badge size="sm" variant="outline">
          Soon
        </Badge>
      ) : item.countSource === "leads" ? (
        <LeadsCount />
      ) : null}
    </>
  );

  if (item.href === undefined) {
    return (
      <span
        aria-disabled="true"
        className={cn(itemClasses, "cursor-default text-subtle-foreground")}
      >
        {content}
      </span>
    );
  }

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      transitionTypes={[transitionType]}
      onClick={() => {
        onNavigate?.();
      }}
      className={cn(
        itemClasses,
        "focus-ring-inset transition-colors duration-fast",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      )}
    >
      {active ? (
        <span
          aria-hidden="true"
          className="absolute inset-y-1.5 -left-3 w-0.75 rounded-r-full bg-sidebar-primary"
        />
      ) : null}
      {content}
    </Link>
  );
}

function LeadsCount(): React.JSX.Element | null {
  const { data } = useQuery(leadSummaryQueryOptions());
  if (data === undefined) {
    return null;
  }
  return (
    <span className="text-xs text-subtle-foreground tabular-nums">{formatNumber(data.total)}</span>
  );
}

function SidebarNavSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading menu" className="flex min-h-0 flex-1 flex-col gap-5">
      {[1, 4, 3].map((count, sectionIndex) => (
        <div key={sectionIndex} className="flex flex-col gap-0.5">
          <Skeleton className="mx-2 mb-1.5 h-3 w-16" />
          {Array.from({ length: count }, (_, itemIndex) => (
            <div key={itemIndex} className="flex h-control-sm items-center gap-2.5 px-2">
              <Skeleton className="size-4 rounded-xs" />
              <Skeleton className="h-3.5 w-24" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function SidebarEnvironmentCard(): React.JSX.Element | null {
  if (clientEnv.appEnv === "production") {
    return null;
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs shadow-xs">
      <p className="flex items-center gap-1.5 font-medium text-foreground">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-highlight" />
        {clientEnv.apiMocking === "enabled" ? "Mock backend" : "Live API"}
      </p>
      <p className="mt-1 text-muted-foreground">
        {clientEnv.apiMocking === "enabled"
          ? "Preview any role or state from your account menu."
          : clientEnv.apiBaseUrl}
      </p>
    </div>
  );
}
