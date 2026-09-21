"use client";

import { ComputerIcon, Moon02Icon, Sun03Icon, UserAdd01Icon } from "@hugeicons/core-free-icons";
import { useRouter } from "next/navigation";
import type * as React from "react";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Icon } from "@/components/ui/icon";
import { useSession } from "@/features/session/hooks/use-session";
import { can } from "@/lib/auth/permissions";
import { useTheme } from "@/lib/theme/use-theme";

import { visibleNavSections } from "./navigation";

export interface CommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * ⌘K / Ctrl+K (or "/") — jump to any page the role can use, or run an action.
 * No open/close animation: it is a keyboard tool used many times a day.
 */
export function CommandMenu({ open, onOpenChange }: CommandMenuProps): React.JSX.Element {
  const router = useRouter();
  const { data: session } = useSession();
  const { setPreference } = useTheme();

  const pages = session
    ? visibleNavSections(session.role)
        .flatMap((section) => section.items)
        .filter((item) => item.href !== undefined)
    : [];
  const canCreateLead = session !== undefined && can(session.role, "leads:create");

  const run = (action: () => void): void => {
    onOpenChange(false);
    action();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <Command loop>
        <CommandInput placeholder="Search pages and actions…" />
        <CommandList>
          <CommandEmpty>No matching pages or actions.</CommandEmpty>
          {pages.length > 0 ? (
            <CommandGroup heading="Go to">
              {pages.map((item) => (
                <CommandItem
                  key={item.id}
                  value={item.label}
                  onSelect={() => {
                    run(() => {
                      if (item.href !== undefined) {
                        router.push(item.href);
                      }
                    });
                  }}
                >
                  <Icon icon={item.icon} />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          <CommandSeparator />
          <CommandGroup heading="Actions">
            {canCreateLead ? (
              <CommandItem
                value="Create a new lead"
                onSelect={() => {
                  run(() => {
                    router.push("/leads?newLead=true");
                  });
                }}
              >
                <Icon icon={UserAdd01Icon} />
                Create a new lead
              </CommandItem>
            ) : null}
            <CommandItem
              value="Switch to light theme"
              onSelect={() => {
                run(() => {
                  setPreference("light");
                });
              }}
            >
              <Icon icon={Sun03Icon} />
              Switch to light theme
            </CommandItem>
            <CommandItem
              value="Switch to dark theme"
              onSelect={() => {
                run(() => {
                  setPreference("dark");
                });
              }}
            >
              <Icon icon={Moon02Icon} />
              Switch to dark theme
            </CommandItem>
            <CommandItem
              value="Use system theme"
              onSelect={() => {
                run(() => {
                  setPreference("system");
                });
              }}
            >
              <Icon icon={ComputerIcon} />
              Use system theme
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
