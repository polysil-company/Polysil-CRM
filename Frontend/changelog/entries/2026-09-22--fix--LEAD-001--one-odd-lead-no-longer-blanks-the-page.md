---
date: 2026-09-22
type: fix
title: One odd lead no longer blanks the page, and a source the administrators renamed still filters
dataIds:
  - LEAD-001
  - LEAD-002
  - MSTR-002
  - DS-001
author: Nakul Srivastava
breaking: false
---

## Before

Six things the leads screens got wrong once the dev API — rather than the mock backend — was answering:

- **One malformed lead failed the whole page.** `GET /leads` was read as `z.array(leadSchema)`, so a single record the backend sent with an empty name, territory or system replaced twenty-four good leads with "We received data we couldn't read". The count endpoint already guarded against exactly this; the list did not.
- **A source code outside `[a-z0-9_]` silently disappeared.** The URL parser only accepted lowercase words joined by underscores. The lists are edited by administrators, so the day someone adds `agri-fair`, choosing that source wrote it to the URL, the parser read it back as nothing, and the pill snapped to unset — a filter that looked like it did nothing at all.
- **A chosen Source could not be un-chosen.** Source is optional on the New lead form, but `LookupSelect` offered no way back to "not set": once picked, it could only be swapped.
- **The New lead dialog left a timer running.** After a save it waits 700 ms before closing. Nothing cancelled that timer, and `useAsyncAction` calls `onSuccess` whether or not the dialog is still mounted, so leaving the page inside that window reset a form that was gone and wrote to the next page's URL.
- **"Loading sources…" was shown for a list that had loaded and was empty**, because the pill's message only told an error apart from everything else.
- **"Previous page" stayed clickable while a page loaded** and silently did nothing. "Next page" disabled itself properly; the two behaved differently for the same reason.

## Now

- **The list reads leads one at a time.** A lead that breaks the contract is left out, counted, and logged (`left out 1 lead(s) that did not match the contract`), and the rest of the page is shown. A page where *no* lead matches is still a contract violation — that is a change of shape, not one bad record. The new `cursorPageSchema` in `lib/api/pagination.ts` does this for any cursor-paged list, so quotations and orders inherit it; `CursorPage` carries `skipped` alongside the rows.
- **Lookup codes are checked for shape, not spelling:** letters, digits, `_`, `-` and `.`. `agri-fair` and `qr.code` filter as they should. A code the backend does not know is still the backend's to refuse.
- **Optional lookup fields can be emptied.** `LookupSelect` takes `clearable`, which adds a "Not set" row; the field then shows its placeholder again. Fields that need a value — Irrigation system — do not get the row, and ignore a null.
- **The dialog's close timer is cancelled** when the dialog unmounts and whenever the form resets.
- **The Source pill says which of the three it is:** loading, failed, or nothing set up yet.
- **Both paging buttons are disabled together** while a page change is in flight. `DataTable` takes `isPaging` instead of the caller folding it into `hasNextPage`.
- **The search term is trimmed once**, in `useLeadListParams`, so a hand-edited `?q=%20` no longer counts as an active filter while sending nothing.

## Discussion

The row-tolerance change is the one with a real trade-off: a backend that quietly drops a required field now shows a slightly short page instead of failing loudly. That is the right way round for a sales team working a list — but only because the drop is never silent for us: it is counted on the page and logged as a warning with the Data ID, and a page where nothing parses still fails hard. The alternative, relaxing `.min(1)` across the wire schema, would have bought the same resilience by giving up the contract itself.

`clearable` is opt-in rather than the default because most lookups back a required field, and a "Not set" row on those is a way to make a form invalid by accident.

The widened code pattern is deliberately a shape check, not an allow-list: the frontend cannot know what an administrator will type next, and the backend rejects codes it does not have. Worth confirming with the backend what its lookup codes actually allow (Frontend-Scope §10).

## Files changed

- `src/lib/api/pagination.ts` — `cursorPageSchema`, `skipped` on `CursorPage`, `PageMetaWire`.
- `src/features/leads/api/leads.schemas.ts`, `leads.api.ts` — the list uses it; `listLeads` logs what was left out.
- `src/features/leads/hooks/use-lead-list-params.ts` — widened code pattern, search trimmed once.
- `src/features/lookups/components/lookup-select.tsx` — `clearable`, placeholder helper.
- `src/features/leads/components/new-lead-dialog.tsx` — cancelled timer, clearable Source.
- `src/features/leads/components/leads-toolbar.tsx` — three messages for the Source pill.
- `src/components/patterns/data-table/data-table.tsx`, `leads-table.tsx` — `isPaging`, with a `Paging` story.

## Tests

11 new unit tests, 360 passing.

- `lib/api/pagination.test.ts` — a clean page, a page with two bad rows, a page where nothing parses (and the message naming the first failure), an empty page.
- `features/leads/api/leads.test.ts` — `listLeads` keeps the good lead and counts the bad one; a page where nothing matches still fails as `CONTRACT_VIOLATION`.
- `features/leads/components/leads-ui.test.tsx` — `?source=agri-fair` reaches the request instead of being dropped.
- `features/lookups/components/lookup-select.test.tsx` — the list's rows by name, emptying a clearable field, and no "Not set" row on a required one.
- `components/patterns/data-table/data-table.test.tsx` — both paging buttons disabled while a page loads.
