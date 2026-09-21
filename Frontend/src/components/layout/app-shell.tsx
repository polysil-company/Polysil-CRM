"use client";

import { useState } from "react";
import type * as React from "react";

import { useKeyboardShortcut } from "@/hooks/use-keyboard-shortcut";

import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";
import { CommandMenu } from "./command-menu";
import { CommandMenuContext } from "./command-menu-context";

/**
 * APP-001 · The signed-in application frame: sidebar on the canvas, content in
 * an inset panel. The sidebar and header carry view-transition names so they
 * stay still while pages slide underneath.
 */
export function AppShell({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [commandOpen, setCommandOpen] = useState(false);

  useKeyboardShortcut({ key: "k", mod: true, allowInEditable: true }, () => {
    setCommandOpen((open) => !open);
  });
  useKeyboardShortcut({ key: "/" }, () => {
    setCommandOpen(true);
  });

  const commandMenu = {
    open: () => {
      setCommandOpen(true);
    },
  };

  return (
    <CommandMenuContext value={commandMenu}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:layer-toast focus:rounded-md focus:bg-popover focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-md"
      >
        Skip to content
      </a>
      <div className="flex h-dvh overflow-hidden bg-background">
        <AppSidebar className="hidden w-sidebar shrink-0 vt-app-sidebar lg:flex" />
        <div className="flex min-w-0 flex-1 flex-col lg:py-2 lg:pr-2">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-panel text-panel-foreground lg:rounded-2xl lg:shadow-panel">
            <AppHeader className="vt-app-header" />
            <main
              id="main-content"
              tabIndex={-1}
              className="min-h-0 flex-1 scrollbar-thin overflow-y-auto outline-none"
            >
              {children}
            </main>
          </div>
        </div>
      </div>
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
    </CommandMenuContext>
  );
}
