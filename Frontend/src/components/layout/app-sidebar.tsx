"use client";

import { RefreshIcon, Search01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { leadStatsQueryOptions } from "@/features/leads/api/leads.queries";
import { conversationListQueryOptions } from "@/features/messages/api/messages.queries";
import { useSession } from "@/features/session/hooks/use-session";
import { useModifierKeyLabel } from "@/hooks/use-modifier-key";
import { clientEnv, type ApiMockingMode, type AppEnv } from "@/lib/env/client";
import { formatNumber } from "@/lib/format";
import { useSidebar } from "@/lib/sidebar/use-sidebar";
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

/** What the environment card calls the backend, by mocking mode. */
const BACKEND_LABELS: Readonly<Record<ApiMockingMode, string>> = {
  enabled: "Mock backend",
  partial: "Dev API + mocks",
  disabled: "Live API",
};

/** Clears the 56px rail, so a tooltip never covers the sidebar edge. */
const RAIL_TOOLTIP_OFFSET = 18;

/**
 * Nothing moves when the sidebar collapses: the rail is 56px with 12px gutters, so every
 * row is 32px wide and an icon at `px-2` is already centred. Rows keep their padding in
 * both states; only the width animates, labels fade, and rail icons grow with a transform.
 */
const LABEL_FADE_CLASSES =
  "min-w-0 flex-1 overflow-hidden whitespace-nowrap transition-opacity duration-fast sidebar-collapsed:opacity-0";

type Navigate = (() => void) | undefined;

/**
 * The desktop sidebar. It follows the `sidebar-collapsed:` variant (APP-005): an icon
 * rail whose names move into tooltips. Visuals come from CSS, set before first paint;
 * `collapsed` only switches the tooltips on.
 */
export function AppSidebar({ className }: { className?: string }): React.JSX.Element {
  const { collapsed } = useSidebar();

  return (
    <aside
      id="app-sidebar"
      aria-label="Sidebar"
      data-follows-sidebar
      className={cn("flex h-dvh flex-col overflow-x-hidden bg-sidebar", className)}
    >
      <SidebarContent collapsed={collapsed} />
    </aside>
  );
}

/** Shared by the desktop sidebar and the mobile menu sheet, which never collapses. */
export function SidebarContent({
  onNavigate,
  collapsed = false,
}: {
  onNavigate?: Navigate;
  collapsed?: boolean;
}): React.JSX.Element {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 px-3 py-4">
      <SidebarBrand />
      <SidebarSearchButton onOpen={onNavigate} collapsed={collapsed} />
      <SidebarNav onNavigate={onNavigate} collapsed={collapsed} />
      <SidebarEnvironmentCard collapsed={collapsed} />
    </div>
  );
}

function SidebarBrand(): React.JSX.Element {
  return (
    // px-0.5: the 28px mark's centre lands on the nav icons' centre (16px), in both states.
    <div className="flex h-8 items-center gap-2 px-0.5">
      <BrandMark className="size-7 shrink-0" />
      <div className={cn(LABEL_FADE_CLASSES, "flex flex-col")}>
        <span className="truncate text-sm font-semibold text-foreground">Polysil</span>
        <span className="truncate text-xs text-muted-foreground">CRM & DMS</span>
      </div>
      {clientEnv.appEnv === "production" ? null : (
        <Badge size="sm" variant="highlight" className="ml-auto sidebar-collapsed:hidden">
          {ENVIRONMENT_LABELS[clientEnv.appEnv]}
        </Badge>
      )}
    </div>
  );
}

function SidebarSearchButton({
  onOpen,
  collapsed,
}: {
  onOpen: Navigate;
  collapsed: boolean;
}): React.JSX.Element {
  const { open } = useCommandMenu();
  const modifier = useModifierKeyLabel();
  const shortcut = (
    <KbdGroup>
      <Kbd>{modifier}</Kbd>
      <Kbd>K</Kbd>
    </KbdGroup>
  );

  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={() => {
              onOpen?.();
              open();
            }}
            className="flex h-control-sm w-full press-scale items-center gap-2 rounded-md border border-border bg-card px-2 text-sm text-subtle-foreground shadow-xs hover:border-border-strong hover:text-muted-foreground sidebar-collapsed:text-muted-foreground"
          />
        }
      >
        <Icon
          icon={Search01Icon}
          size="sm"
          className="shrink-0 transition-transform duration-base ease-in-out sidebar-collapsed:scale-125"
        />
        <span className={cn(LABEL_FADE_CLASSES, "text-left")}>Find…</span>
        <span className="contents sidebar-collapsed:hidden">{shortcut}</span>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={RAIL_TOOLTIP_OFFSET}>
        Find…
        {shortcut}
      </TooltipContent>
    </Tooltip>
  );
}

function SidebarNav({
  onNavigate,
  collapsed,
}: {
  onNavigate: Navigate;
  collapsed: boolean;
}): React.JSX.Element {
  const pathname = usePathname();
  const session = useSession();

  if (session.status === "pending") {
    return <SidebarNavSkeleton />;
  }

  if (session.status === "error") {
    const retry = (): void => {
      void session.refetch();
    };

    return (
      <div
        role="alert"
        className="flex flex-1 flex-col items-start gap-2 px-2 text-sm text-muted-foreground sidebar-collapsed:items-center sidebar-collapsed:px-0"
      >
        <span className="sidebar-collapsed:sr-only">Couldn&apos;t load your menu.</span>
        <Button variant="outline" size="xs" className="sidebar-collapsed:hidden" onClick={retry}>
          Try again
        </Button>
        {/* The rail has no room for words: an icon button with the same action. */}
        <Tooltip disabled={!collapsed}>
          <TooltipTrigger
            render={
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Try loading the menu again"
                className="hidden sidebar-collapsed:inline-flex"
                onClick={retry}
              />
            }
          >
            <Icon icon={RefreshIcon} />
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={RAIL_TOOLTIP_OFFSET}>
            Couldn&apos;t load your menu. Try again.
          </TooltipContent>
        </Tooltip>
      </div>
    );
  }

  const sections = visibleNavSections(session.data.permissions, session.data.userType);
  const items = sections.flatMap((section) => section.items);
  const activeIndex = items.findIndex((item) => isNavItemActive(item, pathname));

  return (
    <nav
      aria-label="Primary"
      className="-mx-3 min-h-0 flex-1 scrollbar-thin overflow-x-hidden overflow-y-auto px-3"
    >
      {sections.map((section) => (
        <div
          key={section.id}
          className="mb-5 border-b border-transparent transition-[margin,padding,border-color] duration-base ease-in-out last:mb-0 sidebar-collapsed:mb-2.5 sidebar-collapsed:border-sidebar-border sidebar-collapsed:pb-2 sidebar-collapsed:last:border-transparent sidebar-collapsed:last:pb-0"
        >
          {/* In the rail the heading folds to a hairline; its text stays for screen readers. */}
          <h2 className="h-5.5 overflow-hidden px-2 text-2xs font-medium tracking-wider whitespace-nowrap text-subtle-foreground uppercase transition-[height,opacity] duration-base ease-in-out sidebar-collapsed:h-0 sidebar-collapsed:opacity-0">
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
                    collapsed={collapsed}
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
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  transitionType: "nav-forward" | "nav-back";
  onNavigate: Navigate;
  collapsed: boolean;
}): React.JSX.Element {
  const itemClasses =
    "group/item relative flex h-8 items-center gap-2.5 rounded-md px-2 text-sm font-medium";
  const planned = item.href === undefined;

  const content = (
    <>
      {/* Rail icons grow 16 → 20px by transform, so they read clearly without moving. */}
      <Icon
        icon={item.icon}
        className={cn(
          "shrink-0 transition-[color,transform] duration-base ease-in-out sidebar-collapsed:scale-125",
          active
            ? "text-foreground"
            : "text-subtle-foreground group-hover/item:text-foreground sidebar-collapsed:text-muted-foreground",
        )}
      />
      <span className={LABEL_FADE_CLASSES}>{item.label}</span>
      {planned ? (
        <Badge size="sm" variant="outline" className="sidebar-collapsed:hidden">
          Soon
        </Badge>
      ) : item.countSource === "leads" ? (
        <LeadsCount />
      ) : item.countSource === "messages" ? (
        <UnreadMessagesCount />
      ) : null}
    </>
  );

  const trigger =
    item.href === undefined ? (
      <span
        aria-disabled="true"
        className={cn(itemClasses, "cursor-default text-subtle-foreground")}
      />
    ) : (
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
      />
    );

  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger render={trigger}>
        {active ? (
          <span
            aria-hidden="true"
            className="absolute inset-y-1.5 -left-3 w-0.75 rounded-r-full bg-sidebar-primary"
          />
        ) : null}
        {content}
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={RAIL_TOOLTIP_OFFSET}>
        {item.label}
        {planned ? <span className="text-background/70">· Soon</span> : null}
      </TooltipContent>
    </Tooltip>
  );
}

/** LEAD-004 · How many leads the user can see, from the lead stats. */
function LeadsCount(): React.JSX.Element | null {
  const { data } = useQuery(leadStatsQueryOptions());
  if (data === undefined) {
    return null;
  }
  return (
    <span className="text-xs text-subtle-foreground tabular-nums sidebar-collapsed:hidden">
      {formatNumber(data.total)}
    </span>
  );
}

/** MSG-001 · Unread messages, from the same polled list the Messages page uses. */
function UnreadMessagesCount(): React.JSX.Element | null {
  const { data } = useQuery(conversationListQueryOptions());
  if (data === undefined || data.unreadTotal === 0) {
    return null;
  }
  return (
    <>
      <Badge size="sm" variant="primary" className="tabular-nums sidebar-collapsed:hidden">
        <span className="sr-only">Unread messages: </span>
        {formatNumber(data.unreadTotal)}
      </Badge>
      {/* The rail has no room for the number: a dot on the icon says something is new. */}
      <span
        aria-hidden="true"
        className="absolute top-1 right-1 hidden size-2 rounded-full bg-primary ring-2 ring-sidebar sidebar-collapsed:block"
      />
    </>
  );
}

function SidebarNavSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading menu"
      className="flex min-h-0 flex-1 flex-col gap-5 sidebar-collapsed:gap-3"
    >
      {[1, 4, 3].map((count, sectionIndex) => (
        <div key={sectionIndex} className="flex flex-col gap-0.5">
          <Skeleton className="mx-2 mb-1.5 h-3 w-16 sidebar-collapsed:hidden" />
          {Array.from({ length: count }, (_, itemIndex) => (
            <div key={itemIndex} className="flex h-8 items-center gap-2.5 px-2">
              <Skeleton className="size-4 shrink-0 rounded-xs sidebar-collapsed:scale-125" />
              <Skeleton className="h-3.5 w-24 sidebar-collapsed:hidden" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function SidebarEnvironmentCard({ collapsed }: { collapsed: boolean }): React.JSX.Element | null {
  if (clientEnv.appEnv === "production") {
    return null;
  }

  const backend = BACKEND_LABELS[clientEnv.apiMocking];

  return (
    <>
      <div className="rounded-lg border border-border bg-card p-3 text-xs shadow-xs sidebar-collapsed:hidden">
        <p className="flex items-center gap-1.5 font-medium text-foreground">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-highlight" />
          {backend}
        </p>
        <p className="mt-1 text-muted-foreground">
          {clientEnv.apiMocking === "enabled"
            ? "Preview any role or state from your account menu."
            : clientEnv.apiMocking === "partial"
              ? "Real sign-in. Leads, dashboard, notifications and messages are still mocked."
              : clientEnv.apiBaseUrl}
        </p>
      </div>
      {/* The rail keeps the environment signal as a dot; its name is in the tooltip. */}
      <Tooltip disabled={!collapsed}>
        <TooltipTrigger
          render={
            <span
              role="img"
              aria-label={`${ENVIRONMENT_LABELS[clientEnv.appEnv]} · ${backend}`}
              className="hidden size-control-sm items-center justify-center self-center sidebar-collapsed:flex"
            />
          }
        >
          <span aria-hidden="true" className="size-1.5 rounded-full bg-highlight" />
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={RAIL_TOOLTIP_OFFSET}>
          {ENVIRONMENT_LABELS[clientEnv.appEnv]} · {backend}
        </TooltipContent>
      </Tooltip>
    </>
  );
}
