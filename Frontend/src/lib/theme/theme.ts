/**
 * Theme preference shared by the blocking init script (runs before paint)
 * and the client-side store. Written in-house instead of next-themes, which is
 * unmaintained and triggers React 19's "script tag while rendering" error.
 */

export const THEME_STORAGE_KEY = "polysil:theme";

export const THEME_PREFERENCES = ["light", "dark", "system"] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number];

export type ResolvedTheme = "light" | "dark";

export const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

export function isThemePreference(value: unknown): value is ThemePreference {
  return THEME_PREFERENCES.some((preference) => preference === value);
}

export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark: boolean,
): ResolvedTheme {
  if (preference === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return preference;
}

/**
 * Inline script placed in <head> by the root layout. It sets the `dark` class
 * before the first paint, so there is no flash of the wrong theme.
 * Keep it tiny, dependency-free and wrapped in try/catch.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var p=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=p==="dark"||(p!=="light"&&window.matchMedia(${JSON.stringify(
  DARK_MEDIA_QUERY,
)}).matches);document.documentElement.classList.toggle("dark",d);}catch(e){}})();`;
