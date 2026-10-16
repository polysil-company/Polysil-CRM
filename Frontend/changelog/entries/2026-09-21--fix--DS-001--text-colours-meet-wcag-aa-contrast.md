---
date: 2026-09-21
type: fix
title: Small grey text and teal links meet WCAG AA contrast in light mode
dataIds:
  - DS-001
author: Nakul Srivastava
breaking: false
---

## Before

CI failed on the Storybook accessibility and Playwright smoke checks (PR #3). axe flagged text below the 4.5:1 minimum in light mode:

- `text-subtle-foreground` (`#77746f`) — sidebar section headings, the leads count, the "Ref" label on error references: 4.23:1 on the canvas, 3.8–3.87:1 on tinted rows and cards.
- The `link` button, which used `text-primary` (`#00847b`, teal-600): 4.17:1.

The checks first ran when the root CI workflows arrived, so the foundation had never been measured against them.

## Now

- `--subtle-foreground` is `sand-600` in light mode — the same shade as `--muted-foreground`. Every use passes, including the 37 in the sidebar, bell and messages. Dark mode is unchanged.
- A new `--primary-text` token (`teal-700` in light, `teal-400` in dark) colours teal _text_: the `link` button and the unread time in Messages. `--primary` stays teal-600 for fills, where white text on it passes, and for icons, spinners and sparklines, which need only 3:1.

## Discussion

- **Why the two greys now match in light mode.** On the tinted rows (`#eae8e5`) the lightest grey that passes is about 51% L — a hair from muted's 50%. A separate lighter tier can't exist at AA, so small meta text keeps its place through size and weight (11–12px, uppercase headings) instead of colour.
- **Why a text token, not a darker `--primary`.** Darkening `--primary` would darken every button and the brand across the app to fix two pieces of text.
- **Rejected:** changing each flagged element to `text-muted-foreground` one by one. The token is wrong, not the call sites, and new screens would repeat it.

## Files changed

- `src/styles/tokens.css` — `--subtle-foreground` in light mode; new `--primary-text` for both themes
- `src/components/ui/button-variants.ts` — the `link` variant uses `text-primary-text`
- `src/features/messages/components/conversation-list.tsx` — the unread time uses `text-primary-text`
- `Docs/Design-System.md` — the colour table and why the greys match

## Tests

- `npm run test:storybook` — the Button › Variants and Error state stories that failed now pass the axe checks
- `e2e/smoke.spec.ts` — the Dashboard and Leads accessibility checks cover the sidebar; run in CI
