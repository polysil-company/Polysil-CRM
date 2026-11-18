---
date: 2026-10-18
type: feature
title: Search and help
dataIds:
  - BOT-001
  - BOT-002
author: Nakul Srivastava
breaking: false
---

## Before

The Ctrl+K menu could jump to a page, start a new lead or switch the theme. It couldn't find a record or anything else the user may do. Nothing in the app listed everything a role can do.

## Now

Built to `in-app-assistant.md` (FS-045) and the generated `assistant.md`. As the spec says, this is a search box, not a chatbot.

**The Ctrl+K menu** (BOT-001)

- It opens as before with Ctrl+K or ⌘K, with `/`, or from the search button on a phone. It now searches pages, actions and records.
- **Actions** come from `GET /assistant`, so they follow the user's permissions. A starter set shows before anything is typed, then the best matches. An action that starts something ("New quotation") shows a plus.
- **Records** appear from 3 characters:
  - leads and customers by number, mobile or name;
  - quotations, orders and complaints by number, or by serial alone.
  - Each shows its label and its kind, and choosing one opens its page.
- The request waits for a 250 ms pause. A newer search drops the older one, and the last answer stays on screen meanwhile.
- **Go to** (pages) and **Preferences** (theme, and Help) still filter in the browser. If the search fails, a line says records can't be searched just now and the pages still work.
- The backend names a screen with a stable key, and `assistant-routes.ts` maps each key to this app's route. A "new" screen without a route of its own opens the page whose button starts it:
  - a new task opens Tasks;
  - a new campaign opens Campaigns;
  - recording a payment opens Receipts;
  - ordering marketing material opens Marketing material.
- A key or record kind this app doesn't know yet is left out, never shown broken.
- The menu's long-standing separator broke the listbox's accessibility rules (axe: `aria-required-children`). The group headings already separate the groups, so it is gone.

**Help** (`/help`, BOT-002)

- **Help** under Overview, for everyone signed in, and in the menu.
- Everything the user may do (`GET /assistant/actions`), grouped by module, each a link to where it starts, with a filter.
- It says how to open the search: the keys on a computer, the search button on a touch screen.
- Loading, empty ("Nothing matches", or no actions for this role), and error with a retry.

**Mock**

- A stand-in for the backend's catalogue of 37 actions, each with the grant it needs. Messages and Company settings are staff only.
- Words in any order, best first.
- Records are scoped like their lists: a dealer finds only what its dealership holds.
- 422 for a `q` over 100 characters or with control characters, and for a `limit` outside 1 to 20. A farmer gets the portal's 403, as for every route outside the portal.

Walked as an admin on a desktop in light mode and a touch phone in dark mode: the starter set, "new quo", "patel" opening Nilesh Patel's lead, "SO/" finding orders, and Help. Axe found nothing, with no sideways scroll. The only console errors came from the lead page's server-side fetch, which tries to reach a real backend that the mock sandbox doesn't run.

## Discussion

- **The walk found three things, all fixed here:**
  - the separator's axe violation;
  - the record kind's contrast on a selected row in dark mode;
  - "Sales order" wrapping on a phone.
- **Server results are kept by cmdk with the typed text as a keyword.** The server has already matched them, and cmdk's own filter would otherwise hide a record found by mobile. Pages still filter locally, so they rank among the results as before.
- **"Create a new lead" is no longer a fixed item.** The server's **New lead** replaces it, and it shows only to those who may create leads.
- **The catalogue is the backend's.** The mock's titles, hints and grants stand in for it. Staging will show the real wording.
- **This is item 36.** Items 37 (a consolidated order) and 38 (the dealer portal walk) follow.

## Files changed

- `src/features/assistant/api/assistant.schemas.ts`, `.api.ts`, `.queries.ts`: new. These hold the contract with its screen keys, the search and the action list.
- `src/features/assistant/lib/assistant-routes.ts`: new, screen keys to routes, and opening a record.
- `src/features/assistant/lib/assistant-labels.ts`: new, module headings and grouping.
- `src/features/assistant/components/help-page.tsx`: new; `src/app/(app)/help/page.tsx`: new route.
- `src/components/layout/command-menu.tsx`: the server search, Actions and Records, Preferences, no separator.
- `src/components/layout/navigation.ts`: the Help item; `navigation.test.ts`: Help shows to everyone.
- `src/components/layout/app-header.tsx`: the search button's name.
- Mock: `src/mocks/data/assistant.ts`, `src/mocks/handlers/assistant.ts` (new), `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: BOT-001, BOT-002.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/assistant/*`.

## Tests

`src/features/assistant/components/assistant.test.tsx`, 11 tests:

- `[BOT-001] Assistant search (contract)`:
  - a starter set, and records only from 3 characters;
  - words in any order, best first;
  - a quotation by its serial alone;
  - a dealer's records and actions scoped;
  - 422 for a long `q` or a `limit` out of range;
  - an unknown screen or kind left out.
- `[BOT-001] CommandMenu`:
  - an action the server matched opens its page;
  - a lead found by its number opens, and the menu closes;
  - pages still work when the search fails.
- `[BOT-002] Help page`:
  - actions by module, and the filter;
  - a dealer sees only their own.

To check by hand in the mock, as an admin:

1. Press Ctrl+K and type `patel`. Choose a lead.
2. Press Ctrl+K and type `new quo`. Choose **New quotation**.
3. Open Overview → **Help** and filter by `payment`.
