import { createLogger } from "@/lib/logger";

import {
  isSidebarState,
  SIDEBAR_ATTRIBUTE,
  SIDEBAR_STORAGE_KEY,
  type SidebarState,
} from "./sidebar";

/**
 * A tiny external store for the sidebar state, read with `useSyncExternalStore`.
 * Syncs across tabs (storage event), like the theme store.
 */

const log = createLogger({ file: "lib/sidebar/sidebar-store.ts", dataId: "APP-005" });

const SERVER_SNAPSHOT: SidebarState = "expanded";

const listeners = new Set<() => void>();
let current: SidebarState | null = null;

function readStoredState(): SidebarState {
  try {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    return isSidebarState(stored) ? stored : "expanded";
  } catch {
    return "expanded";
  }
}

/** Sets or clears the <html> attribute the `sidebar-collapsed:` variant reads. */
export function applySidebarStateToDocument(state: SidebarState): void {
  const root = document.documentElement;
  if (state === "collapsed") {
    root.setAttribute(SIDEBAR_ATTRIBUTE, "collapsed");
  } else {
    root.removeAttribute(SIDEBAR_ATTRIBUTE);
  }
}

function publish(next: SidebarState): void {
  if (current === next) {
    return;
  }
  current = next;
  applySidebarStateToDocument(next);
  for (const listener of listeners) {
    listener();
  }
}

function handleStorage(event: StorageEvent): void {
  if (event.key === SIDEBAR_STORAGE_KEY) {
    publish(readStoredState());
  }
}

export function subscribeSidebar(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener("storage", handleStorage);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      window.removeEventListener("storage", handleStorage);
    }
  };
}

export function getSidebarSnapshot(): SidebarState {
  current ??= readStoredState();
  return current;
}

export function getServerSidebarSnapshot(): SidebarState {
  return SERVER_SNAPSHOT;
}

export function setSidebarState(state: SidebarState): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, state);
  } catch {
    // Storage unavailable: the choice still applies until the page reloads.
  }
  log.info("setSidebarState", "Sidebar state changed", { context: { state } });
  publish(state);
}

export function toggleSidebar(): void {
  setSidebarState(getSidebarSnapshot() === "collapsed" ? "expanded" : "collapsed");
}
