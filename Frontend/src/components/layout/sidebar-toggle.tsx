"use client";

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useKeyboardShortcut } from "@/hooks/use-keyboard-shortcut";
import { useModifierKeyLabel } from "@/hooks/use-modifier-key";
import { SIDEBAR_COLLAPSIBLE_MEDIA_QUERY } from "@/lib/sidebar/sidebar";
import { useSidebar } from "@/lib/sidebar/use-sidebar";
import { cn } from "@/lib/utils";

/**
 * APP-005 · Collapses the desktop sidebar to an icon rail and back — also ⌘B / Ctrl+B.
 * Desktop only: below `lg` the menu sheet takes its place. No animation: it is used
 * many times a day, often from the keyboard.
 */
export function SidebarToggle({ className }: { className?: string }): React.JSX.Element {
  const { collapsed, toggle } = useSidebar();
  const modifier = useModifierKeyLabel();
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";

  useKeyboardShortcut({ key: "b", mod: true }, () => {
    if (window.matchMedia(SIDEBAR_COLLAPSIBLE_MEDIA_QUERY).matches) {
      toggle();
    }
  });

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-md"
            data-follows-sidebar
            aria-label={label}
            aria-controls="app-sidebar"
            aria-expanded={!collapsed}
            className={cn("hidden lg:inline-flex", className)}
            onClick={toggle}
          />
        }
      >
        {/* The icon follows the pre-paint attribute, so it is right before hydration too. */}
        <Icon icon={PanelLeftCloseIcon} className="sidebar-collapsed:hidden" />
        <Icon icon={PanelLeftOpenIcon} className="hidden sidebar-collapsed:block" />
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {label}
        <KbdGroup>
          <Kbd>{modifier}</Kbd>
          <Kbd>B</Kbd>
        </KbdGroup>
      </TooltipContent>
    </Tooltip>
  );
}
