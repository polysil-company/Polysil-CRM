---
date: 2026-10-02
type: fix
title: "Say what each lead stage means, and give long pages their bottom margin"
dataIds:
  - LEAD-007
  - LEAD-001
  - SO-002
  - DS-001
author: Nakul Srivastava
breaking: false
---

## Before

- **Stages had no explanation.** The Stage filter and the Update stage menu listed stages by name only. Someone new couldn't tell Qualified from Contacted. Merged and Dormant meant nothing without asking: nobody moves a lead to either by hand.
- **Long pages had no bottom margin.** On a desktop, the last card of a sales order, quotation or lead touched the bottom edge of the panel. The sales pages share one layout whose container was fixed to the panel's height, so the list tables could scroll inside it. A long detail page overflowed that fixed height, past the container's bottom padding.
- **Faint grey text failed contrast in dark mode.** `subtle-foreground` measured 4.27:1 on the popover background, below the 4.5:1 that small text needs. axe found it in the Update stage menu, as it had in the notification bell.

## Now

- **The Stage filter explains each stage.** Every stage shows one line under its name, in a wider popover that scrolls on a short screen. For example: "Merged: a duplicate, folded into another lead that carries its history. Hidden from the list unless chosen here." The text is always visible rather than in a hover tooltip, because tooltips don't work on phones.
- **The Update stage menu explains too.** It starts with "Now Quoted" and what that stage means. Each move says what it does: "Mark as lost…: asks for the reason. The lead can be reopened later."
- **Screen readers hear the same.** Each checkbox and menu item is named by its label alone and described by its line (`aria-describedby`), so the names stay short.
- **`FilterPill` options take an optional `description`.** Any filter can use it.
- **Long pages keep their bottom margin.** The sales layout's container fills the panel only when it holds a page that asks for it (`data-page-fill`): the leads, quotations and sales orders lists, and their loading states. Detail pages grow and scroll with the panel, keeping 24px below their last card on a desktop and 20px on a phone.
- **`subtle-foreground` is lighter in dark mode,** raised from L 0.60 to 0.63, so it passes 4.5:1 on every surface, the popover included.
- **The filter popover has a name** ("Stage filter"), so screen readers announce it.

## Discussion

- **The stage descriptions follow the backend's rules.** The backend sets Quoted and Negotiation from the quotation. A lost lead reopens at the stage it was lost from. Only the backend's worker sets Dormant. Merged is a duplicate folded into the lead it duplicates.
- **The spacing fix uses CSS, not route checks.** The layout can't tell a list from a detail page without client code; `has-data-page-fill` lets the page say so itself.
- **The contrast fix changes the token, not the components.** Every faint label in a dark popover or card benefits. In light mode the token is unchanged.
- **One axe finding stays: `region`, on menus.** Base UI portals a menu outside the page landmarks. It is a best-practice rule, not WCAG, and it applies to every dropdown in the app.

## Files changed

- **Stage explanations**
  - `src/features/leads/lib/lead-labels.ts`: `LEAD_STAGE_DESCRIPTIONS`.
  - `lib/lead-lifecycle.ts`: `stageActionDescription`.
  - `components/leads-toolbar.tsx`: the stage filter's descriptions.
  - `components/lead-stage-menu.tsx`: the current stage and each move described (`StageMenuItem`).
- **Filter popover** (`src/components/patterns/filter-pill.tsx` and `filter-pill.stories.tsx`)
  - Option descriptions tied to their controls.
  - A wider, scrollable popover, with a name.
  - The `WithDescriptions` story.
- **Spacing**
  - `src/components/patterns/page-container.tsx`: `fill` only with `data-page-fill`.
  - `src/app/(app)/(sales)/{leads,quotations,sales-orders}/page.tsx`, `leads/loading.tsx`, `sales-orders/loading.tsx`: `data-page-fill`.
- **Contrast**
  - `src/styles/tokens.css`, `Docs/Design-System.md`: dark `subtle-foreground` at 0.63.
- **Records**
  - `Docs/Tested-Features.md`.
  - `Docs/screenshots/stage-help/`.

## Tests

- **`src/components/patterns/filter-pill.test.tsx`**: `[LEAD-001] FilterPill with descriptions`. A checkbox is named by its label and described by its line.
- **`src/features/leads/components/leads-ui.test.tsx`**: `[LEAD-001]` the Stage filter explains Merged and Dormant.
- **`src/features/leads/components/lead-stage.test.tsx`**: `[LEAD-007]` the current stage and each move are described. Every earlier test still finds its items by their short names.
- **By hand, with axe,** on a desktop (light) and a phone (dark):
  - the bottom gap is now 24px and 20px, where it was 0;
  - the leads list still scrolls inside its table, and the page itself doesn't scroll;
  - the Stage filter is clean;
  - the menu is clean apart from `region`.
