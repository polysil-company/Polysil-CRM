import { afterEach, describe, expect, it, vi } from "vitest";

import { isThemePreference, resolveTheme, THEME_INIT_SCRIPT, THEME_STORAGE_KEY } from "./theme";
import { getThemeSnapshot, setThemePreference, subscribeTheme } from "./theme-store";

function runInitScript(): void {
  // The script is a constant string that the root layout inlines into <head>.
  new Function(THEME_INIT_SCRIPT)();
}

describe("[APP-002] theme", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark");
    vi.restoreAllMocks();
  });

  it("resolves 'system' against the operating system setting", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(isThemePreference("sepia")).toBe(false);
  });

  it("applies a stored dark preference before first paint", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    runInitScript();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("keeps light when light is stored, even if the OS is dark", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    runInitScript();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("does not throw when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(runInitScript).not.toThrow();
  });

  it("persists a choice, applies it and notifies subscribers", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTheme(listener);

    setThemePreference("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(getThemeSnapshot()).toEqual({ preference: "dark", resolved: "dark" });

    setThemePreference("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
  });
});
