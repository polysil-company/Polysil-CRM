"use client";

import { Menu01Icon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { SidebarContent } from "./app-sidebar";

/** Phones and tablets: the sidebar in a sheet from the left. Closes when a page is chosen. */
export function MobileNav(): React.JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button variant="ghost" size="icon-md" className="lg:hidden" aria-label="Open menu" />
        }
      >
        <Icon icon={Menu01Icon} />
      </SheetTrigger>
      <SheetContent side="left" showCloseButton={false} className="bg-sidebar">
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <SidebarContent
          onNavigate={() => {
            setOpen(false);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}
