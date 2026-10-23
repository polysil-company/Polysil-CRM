import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isSidebarState,
  SIDEBAR_ATTRIBUTE,
  SIDEBAR_INIT_SCRIPT,
  SIDEBAR_STORAGE_KEY,
} from "./sidebar";
import {
  getSidebarSnapshot,
  setSidebarState,
  subscribeSidebar,
  toggleSidebar,
} from "./sidebar-store";

function runInitScript(): void {
  // The script is a constant string that the root layout inlines into <head>.
  new Function(SIDEBAR_INIT_SCRIPT)();
}

describe("[APP-005] sidebar state", () => {
  afterEach(() => {
    document.documentElement.removeAttribute(SIDEBAR_ATTRIBUTE);
    vi.restoreAllMocks();
  });

  it("accepts only the two states", () => {
    expect(isSidebarState("collapsed")).toBe(true);
    expect(isSidebarState("expanded")).toBe(true);
    expect(isSidebarState("hidden")).toBe(false);
  });

  it("marks the page collapsed before first paint when that was saved", () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, "collapsed");
    runInitScript();
    expect(document.documentElement).toHaveAttribute(SIDEBAR_ATTRIBUTE, "collapsed");
  });

  it("leaves the page expanded when nothing or something unknown was saved", () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, "sideways");
    runInitScript();
    expect(document.documentElement).not.toHaveAttribute(SIDEBAR_ATTRIBUTE);
  });

  it("does not throw when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(runInitScript).not.toThrow();
  });

  it("persists a choice, applies it and notifies subscribers", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSidebar(listener);

    setSidebarState("collapsed");
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("collapsed");
    expect(document.documentElement).toHaveAttribute(SIDEBAR_ATTRIBUTE, "collapsed");
    expect(getSidebarSnapshot()).toBe("collapsed");

    toggleSidebar();
    expect(getSidebarSnapshot()).toBe("expanded");
    expect(document.documentElement).not.toHaveAttribute(SIDEBAR_ATTRIBUTE);
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
  });
});
