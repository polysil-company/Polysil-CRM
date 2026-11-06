---
date: 2026-09-28
type: fix
title: Fixes from the code review of the integration-to-staging pull request
dataIds:
  - LEAD-001
  - LEAD-006
  - LEAD-008
  - QUOT-001
  - QUOT-002
  - DS-001
  - APP-001
author: Nakul Srivastava
breaking: false
---

## Before

A code review of `integration` for staging (#11) found, among the frontend changes:

- The lead table's sort arrows changed the arrow and the URL, but the backend doesn't sort yet (BE-001), so the rows stayed newest first while the user believed they were sorted.
- A blank office, territory, price-list or seller name made a whole quotation fail to parse: the page showed an error and the list dropped the row. The backend doesn't guarantee those names are filled.
- The lead page's Quotations card asked the backend to count every time, although it shows no total.
- The table's Next button, when a caller gave no `hasNextPage`, fell back to a page count computed from a capped total (1,000), so it would stop at page 40.
- The note's remaining-character count included spaces at the ends, which the backend trims before checking its 2,000 limit.
- Nested ternaries in the sidebar, the lead history and the partner search, and an `if` without braces in the assign dialog.

## Now

- **No sort arrows on the lead table** until the backend sorts (`BACKEND_SORTS_LEADS`, `TODO(LEAD-001)`). The sort still travels in the URL and the request, so turning them back on is one line.
- **Blank names print "—"** in a quotation: the office, the territory and its level, the price list, the seller's name, GSTIN and state, the place of supply's state, and the seller on the customer's page. Ids still must be present.
- **The Quotations card on a lead doesn't ask for a count** (`countTotal: false`); the Quotations page still does.
- **A capped total never ends the list:** without `hasNextPage`, Next stays on past it.
- **The note counter** counts the trimmed note, as the backend does.
- **Readability:** the three nested ternaries are small helpers (`backendNote`, `stageTone`, `searchStatus`); the `if` has its braces. The sidebar's dev-API note now says what is really mocked — dashboard, notifications and messages — instead of listing leads, which have been real since #8.

## Discussion

Findings not changed, and why:

- **Approval state dropped by the quotation transform:** already carried through, since the discount-approval work (QUOT-007) landed on the branch after the reviewed commit.
- **Em dashes in UI text:** the repository has no copy rule against them (neither `AGENTS.md` nor `Docs/Design-System.md`), and the app uses them consistently. If the team wants that rule, it belongs in `Docs/Design-System.md` first, and then one pass over every string, rather than changing a few.

## Files changed

- `src/features/leads/components/leads-columns.tsx`, `leads-table.tsx` — no sort arrows until BE-001
- `src/features/quotations/api/quotations.schemas.ts` — `displayText` for names the backend may leave blank; `countTotal` on the list parameters
- `src/features/quotations/api/quotations.api.ts`, `components/lead-quotations.tsx` — no count for the lead's card
- `src/components/patterns/data-table/data-table.tsx` — a capped total doesn't end the list
- `src/features/leads/components/lead-note-composer.tsx` — the trimmed length
- `src/components/layout/app-sidebar.tsx`, `src/features/leads/components/lead-timeline.tsx`, `lead-assign-dialog.tsx` — helpers instead of nested ternaries, braces
- `Docs/Tested-Features.md` — the lead list says the sort arrows wait on BE-001

## Tests

- `src/features/leads/components/leads-ui.test.tsx` — `[LEAD-001]` no sort control on Customer or Value
- `src/features/quotations/api/quotations.test.ts` — `[QUOT-002]` a quotation with a blank office, territory, price list and seller name reads, printing "—"
- `src/components/patterns/data-table/data-table.test.tsx` — `[DS-001]` Next stays on past a capped total
- `src/features/leads/components/lead-activity.test.tsx` — `[LEAD-006]` 2,000 characters and trailing spaces is within the limit
