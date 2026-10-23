"use client";

import { useLayoutEffect, useSyncExternalStore } from "react";

import type { SidebarState } from "./sidebar";
import {
  applySidebarStateToDocument,
  getServerSidebarSnapshot,
  getSidebarSnapshot,
  setSidebarState,
  subscribeSidebar,
  toggleSidebar,
} from "./sidebar-store";

export interface UseSidebarResult {
  readonly state: SidebarState;
  /** True when the desktop sidebar is an icon rail. */
  readonly collapsed: boolean;
  readonly setState: (state: SidebarState) => void;
  readonly toggle: () => void;
}

export function useSidebar(): UseSidebarResult {
  const state = useSyncExternalStore(
    subscribeSidebar,
    getSidebarSnapshot,
    getServerSidebarSnapshot,
  );

  // In development, Strict Mode's remount resets <html> to the attributes React manages,
  // clearing the one the init script set. Re-apply the stored state (not `state`, which is
  // the server value during hydration). A no-op in production.
  useLayoutEffect(() => {
    applySidebarStateToDocument(getSidebarSnapshot());
  }, [state]);

  return {
    state,
    collapsed: state === "collapsed",
    setState: setSidebarState,
    toggle: toggleSidebar,
  };
}
