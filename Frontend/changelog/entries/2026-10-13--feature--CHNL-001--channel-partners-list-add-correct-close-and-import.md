---
date: 2026-10-13
type: feature
title: "Channel partners: list, add, correct, close and import"
dataIds:
  - CHNL-001
  - CHNL-002
  - CHNL-003
  - CHNL-004
  - CHNL-005
author: Nakul Srivastava
breaking: false
---

## Before

"Channel partners" in the menu said "Soon". The backend serves the partner admin (`backend/docs/api/partners.md`) and the partner Excel import (`imports.md`, `kind=partners`) on `integration`. Without a screen, the client had no way to add a distributor, or a dealer or sub-dealer under one, before quoting through them.

## Now

- **Channel partners** (`/partners`) is live for staff who read partners.
  - The list is newest first, with a total. Each row shows the type, code, the partner above, territory, contact and active users.
  - Search by name, code or contact person. Filter by type and by Open, Closed, or both (open by default). A partner's page links to the partners under it, which arrive as an "Under …" filter chip.
  - **Download Excel** exports the filtered list. **Show more** pages on, and keeps the rows already shown if the next page fails.
- **A partner's page** has four cards:
  - Where it sits: its type and price tier, the partner above it (linked), its territory, and a link to those under it.
  - Business: GSTIN, PAN, GST registration, active users, and when it was added.
  - Contact.
  - Credit terms, shown to staff only.
  - Actions: **Edit**; **Close** or **Reopen**; **Add a dealer** (or **Add a sub-dealer**) under it. A closed partner says what closing means.
- **New partner** (CHNL-002).
  - Choose Distributor, Dealer or Sub-dealer first. A dealer then asks for its distributor, and a sub-dealer for its dealer, from the open partners of that type.
  - Then the territory, code, business name, GSTIN, PAN, GST registration, contact details and credit terms.
  - The form names what is missing or misshapen before sending. A refusal returns to its field, such as "Already in use." for a used code.
  - Opened from a partner's page, the form starts as the next type down under that partner, in that partner's territory.
- **Edit** (CHNL-003) sends only what changed and says "Nothing changed yet" until something does. A cleared optional field is sent as null. The code, the type and the parent are shown but fixed, and only staff see the territory and credit terms.
- **Close** (CHNL-004) says how many users will be signed out and deactivated. **Reopen** says the partner's users stay deactivated until each is reactivated in Users & roles.
- **Import from Excel** (CHNL-005) reuses the import dialog from MSTR-007.
  - A dealer names its distributor's code, which may be a row in the same file.
  - The review shows each bad row's reason as the backend words it. The preview shows the territory the backend worked out from the state and district.
  - **Import good rows only** adds the rest, parents first.
- **Who sees it.** Admin-Sales and the MD do everything. District and State Managers add, edit, close and reopen partners in their area (`partners.edit`). Field officers and Regional Managers read only. Partner users get no menu item, and the page is closed to them (APP-006).
- Checked on a phone in dark mode and on a desktop in light mode. axe found nothing.

## Discussion

- **Staff only for now.** The backend also lets a distributor or dealer add the next type down under itself from the portal, with no credit terms. That needs a portal menu item and the partner's own id as the parent. Both wait on the client's word: `TODO(CHNL-002)` sits on the nav item, and the question is in the pull request.
- **Credit terms are recorded, not enforced.** The contract says so (H12), and the form's help text says so too.
- **Closing is staff only.** It needs `partners.edit`, and the backend refuses a partner user even with it.
- **Mock changes.**
  - The mock's partners live in `mockDb.partners`, seeded from the shared `MOCK_PARTNERS`, so leads, orders and users still point at the same ids.
  - `/lookups/partners` now reads the same table, so a partner added here can be picked on a lead.
  - District and State Managers gain `partners.create` and `edit` in the mock, as in RBAC.md §6.1. Regional Managers keep view.
- **Import mock.** The mock's partner fields are now the backend's, `GST registered` included. Its row rules follow `domain/imports/rows.py` (`parse_partners`, `finish_partners`): type words, state by name or code, district in that state, codes in use, repeated codes, and parents in the file or already added.

## Files changed

- `src/features/partners/` — new: the contract, calls, queries, mutations and tests; labels; list URL state; the list, detail, form, parent picker and new and edit pages.
- `src/app/(app)/partners/` — new routes: the list, a partner, new and edit.
- `src/components/layout/navigation.ts` — Channel partners is live, staff only.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — CHNL-001 to CHNL-005.
- `src/mocks/data/partners.ts`, `src/mocks/handlers/partners.ts` — new: the partners and their endpoints. Also `db.ts` and `handlers/index.ts`.
- `src/mocks/handlers/imports.ts`, `src/mocks/data/imports.ts` — the partner import's rows and commit.
- `src/mocks/handlers/lookups.ts` — the partner picker reads the partners table.
- `src/mocks/data/permissions.ts` — managers' partner permissions.
- `src/components/layout/navigation.test.ts` — the `/partners` route guard.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/partners/` — records and screens.

## Tests

- `src/features/partners/api/partners.test.ts` — five suites:
  - `[CHNL-001]`: filters, detail, credit terms by permission, parent search.
  - `[CHNL-002]`: create; used code; wrong parent; GSTIN required; shapes; 403.
  - `[CHNL-003]`: only what changed, null clears, a rename reaches the dealers; an empty change is refused.
  - `[CHNL-004]`: close deactivates users, reopen leaves them; 403 for a partner.
  - `[CHNL-005]`: the import, row by row, then the commit under file and existing parents.
- `src/features/partners/components/partners-ui.test.tsx`:
  - The list, the URL filters, the parent chip and empty state, and the actions by role.
  - New partner: the missing fields, the start from a parent, a GSTIN shape, a used code back on its field, no permission.
  - Edit: fixed fields, "Nothing changed yet", a payment-terms check, the save.
  - Detail: the cards, close and reopen with their messages, and a field officer's read-only view.
- `src/components/layout/navigation.test.ts` — `[APP-006]`: `/partners` is open to staff who read partners, and closed to partners and to QA.
- Walked through in the mock at desktop light and phone dark: list, detail, a dealer added under a distributor, close, the import, edit. Also checked: a field officer's list, and a dealer refused at `/partners`.
