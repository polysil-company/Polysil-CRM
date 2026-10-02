# Design system — Polysil CRM

**Version:** 1.0 · **Date:** 2026-09-14 · **Data ID:** DS-001
**Code:** [`src/styles/tokens.css`](../src/styles/tokens.css) — the single source of visual truth.
**Preview:** `npm run storybook` → *Foundations* and every component, in light and dark.

This document explains the *why* and the *how to use*. The CSS file holds the values. They
change together: a change to one without the other is incomplete.

---

## 1. The rules that keep the product consistent

1. **Every visual value lives in `tokens.css`.** Colours, radii, borders, shadows, type sizes,
   font weights, easing curves, durations, stacking layers. Components never contain raw values.
2. **Tailwind's defaults are switched off.** `bg-blue-500`, `text-[13px]`, `rounded-[10px]`,
   `z-50`, `duration-300`, `font-bold` do not exist or fail lint. Only our vocabulary exists.
3. **Change a token once, it changes everywhere** — the app, Storybook and tests read the same file.
4. **A token change needs, in the same PR:** this document updated, a changelog entry of type
   `design`, and a check of Storybook → Foundations in both themes.
5. **New visual need? Add a token, not an exception.** Discuss it in the PR; do not inline it.

What enforces this (you do not need to remember it — the tools do):

| Guard | Catches |
|---|---|
| `better-tailwindcss/no-unknown-classes` | Any class that is not generated from our tokens |
| `better-tailwindcss/no-restricted-classes` | Arbitrary colours, radii, type, spacing, z-index, durations, easings, `!important` |
| `react/forbid-dom-props` (`style`) | Inline styles |
| `src/lib/motion/tokens.test.ts` | JS motion tokens drifting from the CSS tokens |
| Storybook + axe (`npm run test:storybook`) | Accessibility regressions in every story |

---

## 2. Direction — "water and sun"

Polysil sells drip irrigation. The interface borrows two materials from that world and otherwise
stays out of the way — people will work in it for eight hours a day.

- **Sand** (light) and **ink** (dark) neutrals. Light mode is a warm off-white canvas with white
  panels, not clinical grey. Dark mode is a cool charcoal with layered surfaces.
- **Teal — water — is the only action colour.** Primary buttons, links, focus, the active tab.
- **Sun-yellow — sun — marks selection.** Checked rows and checkboxes. Nothing else uses it,
  so a selection is always obvious.
- **Calm categorical colour.** Tags are neutral chips with a small coloured dot, so a table full
  of crops and sources stays readable.
- **Segmented meters** read like a line of drip emitters — a small, deliberate nod to the product.
- **Premium through restraint:** hairline borders, soft elevation, one accent at a time, dense but
  breathable tables, motion that confirms rather than decorates.

Layout: the sidebar sits directly on the canvas; content lives in an inset panel with a large radius
(desktop). On phones the panel goes edge-to-edge. On desktop the sidebar collapses to a 56px icon
rail (⌘B / Ctrl+B, or the button at the left of the top bar); names show in tooltips, and the choice
is remembered per browser. The top bar carries the page title (the one `h1`) and its description,
taken from the navigation map — pages never repeat them.

---

## 3. Colour

Colours are written in OKLCH (perceptually even lightness). Section 1 of the CSS is the raw
palette (`--sand-*`, `--ink-*`, `--teal-*`, `--sun-*` …) — **components never use it directly.**
They use the semantic tokens below.

### Surfaces and text

| Class | Use for | Light | Dark |
|---|---|---|---|
| `bg-background` | App canvas behind sidebar and panel | sand-100 | ink-950 |
| `bg-panel` | Main content panel, table headers | white | ink-900 |
| `bg-card` | Cards, inputs, chips | white | ink-850 |
| `bg-popover` | Menus, dialogs, toasts | white | ink-800 |
| `bg-overlay` | Dialog and sheet backdrop | 32% sand-950 | 55% black |
| `text-foreground` | Primary text | sand-950 | ink-50 |
| `text-muted-foreground` | Secondary text, labels | sand-600 | 68% L |
| `text-subtle-foreground` | Placeholders, meta, disabled | 50% L (as muted) | 63% L: at least 4.5:1 on the darkest surface it sits on, the popover |

### Interaction fills (translucent — they work on any surface)

| Class | Use for |
|---|---|
| `bg-muted` | Resting fills: kbd, segmented controls, tracks |
| `bg-accent` | Hover on rows, menu items, ghost buttons |
| `bg-accent-strong` | Pressed / active navigation item, empty meter segments |

### Actions and meaning

| Class | Use for | Never for |
|---|---|---|
| `bg-primary` / `hover:bg-primary-hover` | The main action on a surface | Decoration, large areas |
| `bg-primary-soft` + `text-primary-soft-foreground` | Selected-but-quiet states, active tab count | Body text backgrounds |
| `text-primary-text` | Teal as text: links, an unread time | Fills — `text-primary` is for icons, spinners and charts, which need only 3:1 |

In light mode `text-subtle-foreground` is as dark as `text-muted-foreground`: a lighter grey fails
4.5:1 on tinted rows and hover states. Separate the two tiers with size and weight, not colour.
| `bg-secondary` / `hover:bg-secondary-hover` | Secondary actions | — |
| `bg-destructive` | Irreversible actions (delete) | Error *messages* (use `danger`) |
| `bg-highlight`, `bg-row-selected` | Selection only | Status, emphasis |
| `text-success` / `bg-success-soft` | Won, completed, positive change | Brand accents |
| `text-warning` / `bg-warning-soft` | Needs attention, negotiation | — |
| `text-danger` / `bg-danger-soft` | Errors, lost, overdue | Destructive *buttons* |
| `text-info` / `bg-info-soft` | New, informational | — |

Status text on its soft background meets 4.5:1 in both themes.

### Lines

| Class | Use for |
|---|---|
| `border-border` | Default hairline: dividers, card edges, table rows (the default border colour) |
| `border-border-strong` | Hover edges, dashed "unset filter" pills |
| `border-input` | Text field borders |
| `border-control` | Checkbox / radio / switch borders — meets 3:1 |
| `outline-ring` | Focus — meets 3:1 |

### Categorical

`bg-tag-{teal,blue,violet,rose,orange,amber,lime,slate}` for tag dots and chart marks, and
`chart-1 … chart-5` for data series. They are never used for text. `toneForLabel("Cotton")` gives
the same colour for the same label everywhere.

---

## 4. Typography

**Typeface:** Geist for the interface, Geist Mono for references, codes and IDs
(`src/app/fonts.ts`, self-hosted at build time). The ₹ sign lives in the `latin-ext` subset, which
is why that subset is loaded. Checked against the production build on 15 September 2026: the
self-hosted Geist and Geist Mono files both contain the ₹ glyph, so amounts never fall back to a
system font.

> TODO(DS-001): agree the typeface with the client.

### Scale — dense, dashboard-first

| Class | Size / line | Use for |
|---|---|---|
| `text-2xs` | 11 / 16 | Counts, overlines, `Ref` labels |
| `text-xs` | 12 / 16 | Captions, table headers, meta, helper text |
| `text-sm` | 13 / 20 | Table cells, navigation, buttons, inputs on desktop |
| `text-base` | 14 / 22 | Body copy (the page default) |
| `text-md` | 16 / 24 | Inputs on touch devices (prevents iOS zoom) |
| `text-lg` | 18 / 26 | Dialog titles |
| `text-xl` | 22 / 28 | Page titles |
| `text-2xl` | 28 / 34 | KPI values |
| `text-3xl`, `text-4xl` | 36, 48 | Public website only |

**Three weights:** `font-normal` 400, `font-medium` 500, `font-semibold` 600. Hierarchy comes from
size and colour, not boldness. `font-bold` does not exist.

**Numbers:** any column or figure that is compared uses `tabular-nums`. Format every number, amount
and date through `@/lib/format` — lint blocks `Intl.*` and `toLocaleString` elsewhere:

- Money: `formatInr(125000)` → ₹1,25,000 · `formatInrCompact(45000000)` → ₹4.5 Cr
- Dates render in IST: `formatDate`, `formatDateTime`, `<RelativeDate>` ("in 2 days")
- Missing values: `EMPTY_VALUE` (—), never "N/A", "-" or "null"

**Copy:** sentence case for everything, including buttons and headings. Say what happens
("Create lead"), not "Submit".

---

## 5. Shape — one knob

`--radius` (10px) drives every radius; set it to `0` and the whole product becomes sharp.

| Class | Size | Use for |
|---|---|---|
| `rounded-xs` | 4 | Checkbox, kbd |
| `rounded-sm` | 6 | Tags, tooltips, small chips |
| `rounded-md` | 8 | Buttons, inputs, menu items |
| `rounded-lg` | 10 | Menus, popovers |
| `rounded-xl` | 14 | Cards, dialogs, table frames |
| `rounded-2xl` | 18 | Main panel, bottom sheets |
| `rounded-full` | — | Pills, avatars, status badges |

**Concentric corners:** an element inside a rounded container gets
`inner radius = outer radius − padding`, so curves stay parallel.

---

## 6. Elevation and borders

Structure comes from hairline borders first, shadow second.

| Class | Use for |
|---|---|
| `shadow-xs` | Buttons, inputs, cards at rest |
| `shadow-sm` | Raised cards |
| `shadow-md` | Menus, popovers, tooltips |
| `shadow-lg` | Dialogs, sheets, toasts, selection bar |
| `shadow-panel` | The main content panel |

Dark mode shadows are deeper and add a faint top highlight, because a black shadow on charcoal
is otherwise invisible.

---

## 7. Space, size and layers

- **4px grid.** Use the spacing scale (`p-3`, `gap-2`, `px-4`). Arbitrary spacing fails lint.
- **Page rhythm:** always wrap page content in `<PageContainer>` (16/24/32px gutters, 20px gaps).
- **Control heights:** `h-control-xs` 24 · `h-control-sm` 30 · `h-control-md` 36 (default) ·
  `h-control-lg` 44. On touch devices, text fields and selects grow to 44px
  (`pointer-coarse:h-control-lg`); small icon buttons extend their hit area invisibly.
- **Layout constants:** `w-sidebar` 248px, `w-sidebar-rail` 56px (collapsed), `h-header` 56px.
- **Page title:** the top bar carries it at `text-lg` with a `text-sm` description — top-bar chrome,
  not a page heading, so it uses the section-title size rather than `text-xl`.
- **Wide tables** scroll inside their own area. Shift + wheel scrolls sideways
  (`useShiftWheelScroll`, built into `DataTable`); at either edge the wheel returns to the page.
- **Table columns** take a width token from `COLUMN_WIDTH_CLASSES`. Give `fill` to every column
  that reads better wide — names, tags — and never to only one: on a large monitor a lone `fill`
  column collects all the leftover width and opens one long gap beside it.
- **Collapsed sidebar:** style it with the `sidebar-collapsed:` variant on anything marked
  `data-follows-sidebar`. Nothing may move: rows keep their padding in both states (a 32px row with
  an icon at `px-2` is already centred in the rail), labels fade with `sidebar-collapsed:opacity-0`,
  rail icons grow with `sidebar-collapsed:scale-125`, and decoration uses `sidebar-collapsed:hidden`.
  The sidebar's width is the one layout property we animate (`duration-base`, `ease-in-out`): one
  element, so the content panel follows the rail instead of jumping.
- **Stacking layers — never raw z-index:**

| Class | Use for |
|---|---|
| `layer-sticky` | Sticky table headers |
| `layer-header` | App header, progress lines over content |
| `layer-overlay` | Non-modal overlays |
| `layer-modal` | Dialogs, sheets and their backdrops |
| `layer-popover` | Menus, selects, popovers (above dialogs) |
| `layer-toast` | Toasts, the selection bar, the skip link |
| `layer-tooltip` | Tooltips — always on top |

---

## 8. Motion

Built on Emil Kowalski's design-engineering principles. Motion confirms, explains or preserves
spatial continuity. It never decorates something people do a hundred times a day.

### When to animate

| How often it happens | Decision | Examples here |
|---|---|---|
| Many times a day, keyboard-driven | **No animation** | Command menu (⌘K), sidebar navigation highlight |
| Tens of times a day | Minimal, ≤ 150ms | Hover colours, checkbox tick, tooltips |
| Occasionally | Standard | Menus, dialogs, sheets, toasts, page transitions |
| Rarely | Can add delight | Success checkmark, first-run moments |

### Tokens

| Easing | Use for |
|---|---|
| `ease-out` — `cubic-bezier(0.23, 1, 0.32, 1)` | Anything entering or exiting (default) |
| `ease-in-out` — `cubic-bezier(0.77, 0, 0.175, 1)` | Things moving on screen (tab indicator, page slide) |
| `ease-drawer` — `cubic-bezier(0.32, 0.72, 0, 1)` | Sheets and phone bottom sheets |

There is no `ease-in`: it makes interfaces feel slow.

| Duration | Value | Use for |
|---|---|---|
| `duration-press` | 120ms | Press feedback |
| `duration-fast` | 150ms | Hover, tooltips |
| `duration-base` | 200ms | Menus, popovers, state swaps |
| `duration-slow` | 300ms | Dialogs, sheets |
| page tokens | 120 / 220 / 320ms | Directional page transitions (CSS only) |

### Patterns — use the utility, do not hand-roll

- **Press:** `press-scale` → scale 0.97 on `:active` (off under reduced motion). Built into buttons.
  Skipped while the element's own popup is open: menus open on mouse-down, so a shrunken trigger
  would make its popup jump on release. The open trigger's background is the feedback instead.
- **Popovers scale from their trigger:** `origin-(--transform-origin)`, starting at 96% — never
  from 0 and never from the centre (dialogs are the exception: they stay centred).
- **Tooltips:** 400ms delay for the first one; neighbours open instantly (`data-instant`).
- **Enter/exit with CSS transitions**, driven by Base UI's `data-starting-style` and
  `data-ending-style`. Transitions can be interrupted mid-way; keyframes restart.
- **Crossfades use a 2px blur** (`blur-2xs`) to hide the double image — see the async button.
- **Directional page transitions:** links pass `transitionTypes={["nav-forward"]}` (deeper, or down
  the sidebar) or `["nav-back"]`. Pages wrap their content in `<PageTransition>`. The sidebar and
  header are anchored so they never slide.
- **JavaScript animation (Motion)** only for layout animation (tab underline), presence (selection
  bar) and springs. Import from `motion/react`; values from `@/lib/motion/tokens`.
- **Custom carets:** `animate-caret-blink` for a caret drawn inside a custom field (`OtpInput`). Pair
  it with `motion-reduce:animate-none`.
- **Ambient decoration** is allowed only where people rarely are — the sign-in brand panel's drip
  lines (`DripField`) animate opacity and transform, and are not drawn at all under reduced motion.
- **Reduced motion:** Motion follows the OS setting (`MotionConfig reducedMotion="user"`), page
  transitions drop to zero duration, press scale and shimmer switch off.

---

## 9. States — every component has all of them

| State | Pattern | Rule |
|---|---|---|
| First load | `…Skeleton` sibling of the component | Mirrors the real layout line for line (same heights, gaps, column widths) |
| Background refetch | `<IndeterminateBar>` | Never replace loaded data with a skeleton |
| Empty | `<EmptyState>` | Explain why, and offer the next step. Different copy for "no data" vs "no matches" |
| Error | `<ErrorState>` | Human title and action; copyable reference (`LEAD-001 · request id`); retry only if it can help |
| Stale data + failed refresh | `<QueryView>` notice | Keep the data, offer retry |
| Async action | `<Button state>` + `useAsyncAction` | Loading ring → drawn check or shake → idle. Width never jumps. Announced to screen readers |
| Disabled | `disabled` / `data-disabled` | 50% opacity, not-allowed cursor; keep focus while busy |
| Not permitted | Hide it | UI gating only — the backend enforces |

`<QueryView>` makes the first four impossible to forget: it will not compile without them.

---

## 10. Components

Three layers, each allowed to use only the layers below it (lint-enforced):

| Layer | Folder | Contains | Knows about the business? |
|---|---|---|---|
| Primitives | `src/components/ui` | shadcn/ui (Base UI) restyled: Button, Badge, Checkbox, RadioGroup, Input, PasswordInput, OtpInput, Select, Combobox, Dialog, Sheet, Menu, Tooltip, Tabs, ToggleGroup, Command, Field, Card, Skeleton, Spinner, Icon … | No |
| Patterns | `src/components/patterns` | DataTable, QueryView, EmptyState, ErrorState, StatCard, Tag/TagList, SegmentedMeter, Sparkline, FilterPill, SingleFilterPill, SearchField, NavTabs, PageContainer … | No |
| Layout | `src/components/layout` | App shell, sidebar, header, command menu, user menu, page transition | Navigation only |
| Features | `src/features/*/components` | Sign-in, leads table, New lead dialog, dashboard, notification bell, messages | Yes |

Every primitive and pattern has a `*.stories.tsx` next to it covering its states in both themes.

### Adding a shadcn component

1. `npx shadcn@latest add <name> --dry-run --view` and read the source.
2. Recreate it in `src/components/ui/<name>.tsx` (do not run `add` blindly — it installs `next-themes`
   and uses classes our tokens do not define).
3. Restyle: token classes only; remove `focus-visible:ring-*` (the global focus outline covers it);
   replace `animate-in`/`animate-out` with `data-starting-style` / `data-ending-style` transitions;
   use `<Icon>`; add `"use client"` if it uses Base UI parts or hooks.
4. Write the story (all variants and states) and a unit test for behaviour it adds.
5. Add a changelog entry of type `design`.

---

## 11. Icons

Hugeicons (free set) through one component:

```tsx
import { Search01Icon } from "@hugeicons/core-free-icons";
import { Icon } from "@/components/ui/icon";

<Icon icon={Search01Icon} />                      // decorative: hidden from screen readers
<Icon icon={Alert02Icon} label="Warning" />       // meaningful: gets a name
```

Sizes `xs` 12 · `sm` 14 · `md` 16 (default) · `lg` 20 · `xl` 24. Stroke 1.75. Inside a button the
button sets the size. Importing `@hugeicons/react` anywhere else fails lint.

---

## 12. Accessibility baseline

- One global focus outline (2px `ring`, 2px offset) on every focusable element; rows and items in
  clipped containers use `focus-ring-inset`.
- Every control has a visible label or an `aria-label`. Icon-only buttons always have one.
- Semantic elements: `<button>`, `<a>`, `<nav>`, `<table>` with `scope`, `aria-sort` and row headers.
- Contrast: body text ≥ 4.5:1, controls and focus ≥ 3:1, in both themes.
- Touch targets ≥ 24px everywhere, 44px for form fields on touch devices.
- Async results are announced (`role="status"`); errors use `role="alert"`.
- A "Skip to content" link is the first focusable element of the app shell.

---

## 13. Open design decisions

| Decision | Status |
|---|---|
| Brand colours and logo | Awaiting assets from the client. Teal is a placeholder; changing it is a token edit. |
| Typeface | Geist proposed; confirm ₹ rendering and client preference. |
| Charts library | Deferred until the first real chart (reports module). |
