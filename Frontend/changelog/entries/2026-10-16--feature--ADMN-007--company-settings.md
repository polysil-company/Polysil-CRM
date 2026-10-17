---
date: 2026-10-16
type: feature
title: Company settings
dataIds:
  - ADMN-007
author: Nakul Srivastava
breaking: false
---

## Before

The backend keeps company-wide rules as settings an administrator changes (FS-036, handover `settings-amend-reopen-contract.md`). Eighteen are seeded today. They decide how an amended order is re-approved, when an order counts as a sale, how a dealer's credit limit is checked, who approves a replacement, how exports and samples are priced, how complaints reopen and escalate, how dealers are rated, and whether farmers have a portal. The frontend had no screen for them, so changing one meant asking the backend team.

## Now

- **Admin → Company settings** (`/settings`), for staff who see masters.
- **Every setting the backend lists, drawn from its kind**, as the backend asks ("render the list generically"):
  - A choice is a set of radio buttons.
  - A whole number has a box, with its range below it ("1 to 1,00,00,000.").
  - Role codes are checkboxes of the staff roles.
  - Bands are four boxes.
  - Each setting says what it does (the backend's description) and when it last changed.
- **In sections:**
  - **Orders:** re-approving an amended order; when an order counts as a sale; a dealer's credit limit; who approves a replacement order; tax on an export; pricing a sample order; the largest sample order.
  - **Complaints:** the days, roles, clock and count for reopening; a complaint that misses its target.
  - **Dealers:** tasks for dealers; the rating's window, payment-days bands and order-value bands.
  - **Customers:** the farmers' portal; sign-in codes to customers in an hour.
  - A key the page doesn't know goes under **Other**, titled from its own name.
- **Choices in words**, per setting: "Only when its value rises", "When its last line ships", "Warn the approvers", "Zero-rated under a LUT", "Ring the bell"…
- **When an order counts as a sale** carries the handover's note: "Changing this recalculates reports and targets for every month."
- **Who approves a replacement order is a chain.** The roles keep the order they're ticked in, and the card says so: "In this order: State Manager, then Regional Manager, then MD / CEO." To move one to the end, untick it and tick it again. Read-only, it reads the same way.
- **Save changes** sends only what changed, all together. Until then the form shows how many changes there are, and **Undo changes**. The toast says "Setting saved" or "Settings saved".
- **Checks before sending:** an empty or broken number, a number out of range, and bands that aren't four rising whole numbers are each named on their setting. A backend refusal comes back on the setting it names.
- **Without `masters.edit`** the values are shown as text, with a line saying only administrators of masters change them.
- Checked on a phone in dark mode and a desktop in light mode. axe found nothing.

## Discussion

- **The backend's code, not the handover's example.**
  - The handover shows five keys and only `key`, `value`, `allowed`, `description` and `updated_at`.
  - The backend's `Setting` (`api/schemas/settings.py`) also sends `kind` (`choice`, `int`, `roles`, `bands`), `min` and `max`, and the page is drawn from those.
  - The migrations (041 to 060) seed 18 keys. The mock seeds the same keys, values and descriptions.
  - A 422 names the bad setting by its bare key (`api/services/settings.py`). The form also takes `values.<key>`, in case the request's own validation answers that way.
- **Titles, sections and choice words are the frontend's.** The backend sends only codes and a description. A new key of a known kind needs no change here to work; it only needs a title and section to read well.
- **A kind the frontend doesn't know** breaks the contract and shows the error state, rather than guessing an editor.
- **The replacement chain's order** comes from its description ("in order, before the Dispatch Manager"). The backend's `kind` is plain `roles`, so the page knows which key is ordered by name. Moving one by unticking is simple but blunt; drag or up and down buttons can follow if the client asks.
- **Who may be ticked.** Both roles settings offer the staff roles from `GET /lookups/roles`; partner roles are left out, because settings are for staff. The backend checks that each replacement approver approves orders, and its refusal shows on the card.
- **Who sees the page.** It sits in Admin under the `masters` module, because changing a setting needs `masters.edit`. The backend lets any staff member read the settings, but in the mock only Admin has `masters`. So other roles meet the access-denied page, and the read-only view is covered by a unit test.
- **`sale_counted_at` on the reports** (`data.filters.sale_counted_at`) arrives with the reports, item 22.

## Files changed

- `src/features/settings/` — new: the contract, calls, query and mutation; the `CompanySettings` page with its editors and checks; tests.
- `src/app/(app)/settings/page.tsx` — new: the route.
- `src/components/layout/navigation.ts` — Company settings in the Admin menu.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — ADMN-007.
- `src/mocks/handlers/settings.ts` — new: the backend's 18 seeded settings and `GET`/`PATCH /settings` with the backend's checks. Also `db.ts` and `handlers/index.ts`.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/settings/` — records and screens.

## Tests

- `src/features/settings/components/company-settings.test.tsx`:
  - The API: read and patch; a value out of range refused on its key; an employee refused.
  - A number, a choice and roles saved together, sending only what changed.
  - The replacement chain: its order shown, a role moved to the end, saved in that order; the Orders section and the sale-counting note.
  - Read-only without `masters.edit`, the chain read in order.
  - An unknown key under Other, with bands drawn from their kind.
- Walked through in the mock as Admin, at desktop light and phone dark: the page, then two settings changed and saved together.
