import {
  DARK_MEDIA_QUERY,
  isThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";

/**
 * A tiny external store for the theme, read with `useSyncExternalStore`.
 * Syncs across tabs (storage event) and follows the OS setting when the
 * preference is "system".
 */

export interface ThemeSnapshot {
  readonly preference: ThemePreference;
  readonly resolved: ResolvedTheme;
}

const SERVER_SNAPSHOT: ThemeSnapshot = { preference: "system", resolved: "light" };

const listeners = new Set<() => void>();
let current: ThemeSnapshot | null = null;

function readStoredPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_MEDIA_QUERY).matches;
}

function snapshotFor(preference: ThemePreference): ThemeSnapshot {
  return { preference, resolved: resolveTheme(preference, systemPrefersDark()) };
}

/** Swaps the class with transitions disabled for one frame, so colours change instantly. */
function applyToDocument(theme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.add("theme-switching");
  root.classList.toggle("dark", theme === "dark");
  // Reading computed style flushes styles while transitions are disabled.
  void window.getComputedStyle(root).colorScheme;
  window.requestAnimationFrame(() => {
    root.classList.remove("theme-switching");
  });
}

function publish(next: ThemeSnapshot): void {
  const changed =
    current === null ||
    current.preference !== next.preference ||
    current.resolved !== next.resolved;
  current = next;
  if (!changed) {
    return;
  }
  applyToDocument(next.resolved);
  for (const listener of listeners) {
    listener();
  }
}

function handleExternalChange(): void {
  publish(snapshotFor(readStoredPreference()));
}

function handleStorage(event: StorageEvent): void {
  if (event.key === THEME_STORAGE_KEY) {
    handleExternalChange();
  }
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener("storage", handleStorage);
    window.matchMedia(DARK_MEDIA_QUERY).addEventListener("change", handleExternalChange);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      window.removeEventListener("storage", handleStorage);
      window.matchMedia(DARK_MEDIA_QUERY).removeEventListener("change", handleExternalChange);
    }
  };
}

export function getThemeSnapshot(): ThemeSnapshot {
  current ??= snapshotFor(readStoredPreference());
  return current;
}

export function getServerThemeSnapshot(): ThemeSnapshot {
  return SERVER_SNAPSHOT;
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage unavailable: the choice still applies until the page reloads.
  }
  publish(snapshotFor(preference));
}
