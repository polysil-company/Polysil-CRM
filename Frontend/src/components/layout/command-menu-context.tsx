"use client";

import { createContext, use } from "react";

export interface CommandMenuControls {
  open: () => void;
}

export const CommandMenuContext = createContext<CommandMenuControls | null>(null);

export function useCommandMenu(): CommandMenuControls {
  const controls = use(CommandMenuContext);
  if (controls === null) {
    throw new Error("useCommandMenu must be used inside <AppShell>.");
  }
  return controls;
}
