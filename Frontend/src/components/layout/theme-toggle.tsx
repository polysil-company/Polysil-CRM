"use client";

import { ComputerIcon, Moon02Icon, Sun03Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { isThemePreference } from "@/lib/theme/theme";
import { useTheme } from "@/lib/theme/use-theme";

export function ThemeToggle(): React.JSX.Element {
  const { preference, resolvedTheme, setPreference } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="ghost" size="icon-md" aria-label="Change theme" />}
      >
        <Icon icon={resolvedTheme === "dark" ? Moon02Icon : Sun03Icon} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={preference}
          onValueChange={(value: unknown) => {
            if (isThemePreference(value)) {
              setPreference(value);
            }
          }}
        >
          <DropdownMenuRadioItem value="light">
            <Icon icon={Sun03Icon} />
            Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Icon icon={Moon02Icon} />
            Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Icon icon={ComputerIcon} />
            System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
