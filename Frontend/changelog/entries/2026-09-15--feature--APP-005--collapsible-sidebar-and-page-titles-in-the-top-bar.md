---
date: 2026-09-15
type: feature
title: Collapsible desktop sidebar, and page titles with descriptions in the top bar
dataIds:
  - APP-005
  - APP-001
  - DS-001
author: Nakul Srivastava
breaking: true
---

## Before

The desktop sidebar was always 248px wide, so content never had the full width. Every page showed its title twice: small in the top bar, then again as a large heading with a description at the top of the content (`PageHeader`). The Sales pages added a third, "Sales", above their tabs.

## Now

**Collapsing the sidebar** — on desktop (1024px and up), a button at the left of the top bar collapses the sidebar to a 56px icon rail and expands it again; ⌘B (Mac) or Ctrl+B does the same. In the rail:

- Nav items, search, "Soon" modules and the environment show as icons. Hovering or focusing one shows its name in a tooltip to the right, with the shortcut where there is one.
- Section headings become hairlines, and stay readable by screen readers. The active page keeps its teal marker.
- The menu skeleton and the "Couldn't load your menu" state have rail versions; retry becomes an icon button.

The choice is remembered per browser and applied before the first paint, so a collapsed sidebar never flashes open on load, and it follows across open tabs. The button's name ("Collapse sidebar" / "Expand sidebar") and `aria-expanded` state tell screen readers what it will do. Phones and tablets keep the menu sheet, which always shows the full sidebar. Light and dark use the same sidebar tokens.

**Page titles** — the top bar now carries the page title (`text-lg`, the page's one `h1`) and, from 640px up, its description on one line. Pages no longer repeat either. The title uses the section-title size, not the page-title size: in a 56px bar it is chrome, not a page heading. A detail page (a lead) shows its section's title without the description, and names itself in the content. Titles and descriptions live beside each page in the navigation map.

## Discussion

- **The width animates (200ms, ease-in-out)** — the one layout property the design system animates. An instant collapse was tried first and felt like a jump, because the content panel moves with the sidebar. Everything inside is arranged so nothing else moves: rows keep their padding in both states (a 32px row with an icon at `px-2` is already centred in the 56px rail), labels and section headings fade and fold, and rail icons grow from 16 to 20px with a transform — larger and in a stronger colour, so they read clearly. Reduced motion turns the width transition off.
- **CSS decides the look, React only the behaviour.** A `sidebar-collapsed:` variant reads `data-sidebar="collapsed"` on `<html>`, set by an inline script from `localStorage` — the same approach as the theme. React state only switches tooltips on and sets the button's label, so nothing depends on hydration to look right. Only elements marked `data-follows-sidebar` respond, which keeps the phone sheet full.
- **localStorage, not a cookie:** a cookie would let the server render the rail, but reading it in the layout makes every page dynamic. The inline script gives the same result without a flash.
- **Breaking:** `PageHeader` is removed (no remaining uses). `h-header` stays 56px: a `text-lg` title over a `text-sm` description fits, and a taller bar took height from the page for no gain. Page actions that used to sit beside the title will need a home in the top bar or the content when the first page needs one.
- **Rejected:** hiding the sidebar completely (people lose their place; the rail keeps navigation one click away); a collapse button at the bottom of the sidebar (far from the title it makes room for, and absent on phones).
- **Not done:** a "Collapse sidebar" action in the command menu; a Storybook story for the shell (layout components have none yet).

## Files changed

- `src/lib/sidebar/sidebar.ts`, `sidebar-store.ts`, `use-sidebar.ts` — the saved state, the pre-paint script, and a store that syncs across tabs and logs changes
- `src/app/layout.tsx` — runs the sidebar script in `<head>`
- `src/styles/tokens.css` — `sidebar-collapsed:` variant, `w-sidebar-rail` (56px)
- `src/components/layout/sidebar-toggle.tsx` — the toggle button, tooltip and ⌘B shortcut
- `src/components/layout/app-sidebar.tsx` — rail layout, tooltips, rail skeleton and error state
- `src/components/layout/app-shell.tsx` — sidebar width follows the state
- `src/components/layout/app-header.tsx` — toggle, larger title as `h1`, description
- `src/components/layout/navigation.ts` — descriptions for built pages; `findPageHeading`
- `src/app/(app)/dashboard/page.tsx`, `loading.tsx`, `src/app/(app)/(sales)/layout.tsx` — in-page titles removed
- `src/components/patterns/page-header.tsx`, `page-header.stories.tsx` — removed
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — APP-005 registered
- `Docs/Design-System.md`, `Docs/Frontend-Architecture.md` — the rail, the variant, the new sizes and where titles live

## Tests

- `src/lib/sidebar/sidebar.test.ts` — `[APP-005] sidebar state`: pre-paint script, unknown values, blocked storage, persist-apply-notify
- `src/components/layout/sidebar-toggle.test.tsx` — `[APP-005] SidebarToggle`: collapse and expand with the saved state and `aria-expanded`; Ctrl+B only on desktop widths
- `src/components/layout/navigation.test.ts` — `[APP-005] page headings in the top bar`: title and description per route; every built page has a description
- `e2e/smoke.spec.ts` — unchanged; its "Dashboard" level-1 heading now comes from the top bar
- By hand: `npm run dev` → collapse with the button and with ⌘B/Ctrl+B, reload (no flash), hover and Tab through the rail, open a second tab. Check a lead's detail page, 360px (no toggle, full sheet), a wide screen, light and dark.
