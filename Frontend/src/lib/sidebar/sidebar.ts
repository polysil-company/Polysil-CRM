/**
 * APP-005 · Whether the desktop sidebar is expanded or collapsed to an icon rail.
 * Shared by the blocking init script (runs before paint) and the client-side store,
 * mirroring the theme in src/lib/theme.
 */

export const SIDEBAR_STORAGE_KEY = "polysil:sidebar";

export const SIDEBAR_STATES = ["expanded", "collapsed"] as const;

export type SidebarState = (typeof SIDEBAR_STATES)[number];

/** Set to "collapsed" on <html>; the `sidebar-collapsed:` variant in tokens.css reads it. */
export const SIDEBAR_ATTRIBUTE = "data-sidebar";

/** The sidebar collapses only from Tailwind's `lg` breakpoint; smaller screens use the menu sheet. */
export const SIDEBAR_COLLAPSIBLE_MEDIA_QUERY = "(min-width: 64rem)";

export function isSidebarState(value: unknown): value is SidebarState {
  return SIDEBAR_STATES.some((state) => state === value);
}

/**
 * Inline script placed in <head> by the root layout. It marks <html> before the
 * first paint, so a collapsed sidebar never flashes open on load.
 * Keep it tiny, dependency-free and wrapped in try/catch.
 */
export const SIDEBAR_INIT_SCRIPT = `(function(){try{if(localStorage.getItem(${JSON.stringify(
  SIDEBAR_STORAGE_KEY,
)})==="collapsed")document.documentElement.setAttribute(${JSON.stringify(
  SIDEBAR_ATTRIBUTE,
)},"collapsed");}catch(e){}})();`;
