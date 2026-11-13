---
date: 2026-10-02
type: api-integration
title: "Backend pick-ups: lead sorting, territory levels, names in assignments,
  awaiting approval, a quotation's order"
dataIds:
  - LEAD-001
  - LEAD-002
  - LEAD-005
  - LEAD-008
  - QUOT-001
  - SO-003
author: Nakul Srivastava
breaking: false
---

## Before

The backend had finished five asks that the frontend did not use yet:

- **Lead list sorting (BE-001).** `GET /leads` sorts by `farmer_name` or `estimated_value`, but the list hid its sort arrows behind a flag, so it was always newest first.
- **Territory levels (BE-005).** A lead may sit in a district, taluka or village, and a state is refused. The New lead picker still offered the state when you typed its name, and the save then failed.
- **Names on assignments (BE-006).** `lead.assigned` events carry `owner_name`, `partner_name` and, on a handover, `previous_owner_name`. The lead's history still said only "changed the owner and the channel partner".
- **Awaiting approval.** Quotation list rows carry `awaiting_approval`, but a draft waiting on a manager looked like any other draft.
- **A quotation's order (BE-019).** `GET /orders` takes `quotation_id`. To find the order carrying an accepted quotation, the quotation page still listed the lead's orders and read up to ten of them one by one.

## Now

- **Lead list.** Customer and Value sort from their column headers, ascending then descending, with `aria-sort` on the header. The sort travels in the URL as before. Changing it starts again from page 1, because the backend refuses a cursor from another order (`422` on `cursor`).
- **New lead.** Typing in the territory picker searches districts, talukas and villages only (`levels=district,taluka,village`). The state no longer shows, so "Guj" reads "No place matches". Opening the picker still lists districts.
- **Lead history.** Assignments name the people:
  - "assigned the lead to Ravi Joshi and made Khodiyar Irrigation the channel partner";
  - "handed the lead from Asha Mehta to Ravi Joshi";
  - "unassigned Asha Mehta".

  An event without names (someone the backend could not name) still reads as before.

- **Quotations.** A draft whose discount waits for a manager shows an amber "Awaiting approval" chip instead of "Draft". It shows in the quotations list, on the lead's quotations card, and on the quotation page, where it is read from the approval request.
- **Place order.** "Open order" is found with one `GET /orders?quotation_id=…&status=<every status but cancelled>` call, instead of one call for the list and up to ten more.
- **Mock backend.**
  - It sorts as the backend does: names ignore case, a lead without a value comes last in both orders, and ties break by id.
  - It filters territories by `levels`, refusing `levels` with `level`, or an unknown level.
  - It refuses a lead in a state.
  - It writes names on assignment events and seeds one assignment per owned lead.
  - It sets `awaiting_approval` on list rows and filters orders by `quotation_id`.

## Discussion

- **No new endpoints and no new Data IDs.** Each item uses an endpoint that was already connected; only a parameter or a field is new. Rows move within Plan §9.1.
- **BE-019 was done but not ticked.** The backend shipped the `quotation_id` filter in #36 (commit c284913, `backend/docs/api/orders.md`) without ticking it. It is ticked here, with a note.
- **"Awaiting approval" replaces "Draft" in the chip** rather than sitting beside it. Tables stay one chip wide, and filtering by Draft still includes these drafts, as on the backend.
- **The `awaiting_approval` field is optional** in the schema, defaulting to false, so a backend from before #30 still parses.
- **What is left from the backend's finished asks:** nothing. Notifications and messages (BE-009, BE-010) are served and connect next. BE-014 (approval threshold amounts) and BE-020 (order links in a lead's history) wait on the backend.

## Files changed

- **Lead list sorting (BE-001)**
  - `src/features/leads/components/leads-columns.tsx`: Customer and Value sortable; the `BACKEND_SORTS_LEADS` flag is removed.
  - `leads-table.tsx`, `api/leads.schemas.ts`: comments updated.
  - `src/mocks/handlers/leads.ts`: `sortLeads` sorts as the backend does.
- **Territory levels (BE-005)**
  - `src/features/lookups/api/lookups.schemas.ts`, `lookups.api.ts`: `levels` on the territory search.
  - `components/territory-picker.tsx`: a `levels` prop.
  - `src/features/leads/api/leads.schemas.ts`: `LEAD_TERRITORY_LEVELS`.
  - `components/new-lead-dialog.tsx`: passes them.
  - `src/mocks/handlers/lookups.ts`, `handlers/leads.ts`: the `levels` filter and its refusals; a lead in a state refused.
- **Names on assignments (BE-006)**
  - `src/features/leads/lib/timeline-entries.ts`: `AssignmentChange` with names, `previousOwnerName`, `assignmentSentence`.
  - `components/lead-timeline.tsx`: uses it.
  - `src/mocks/handlers/leads.ts`, `src/mocks/data/timeline.ts`: names on assignment events.
- **Awaiting approval**
  - `src/features/quotations/api/quotations.schemas.ts`: `awaitingApproval` on list rows.
  - `components/quotation-status-badge.tsx`: the "Awaiting approval" chip.
  - `quotations-columns.tsx`, `lead-quotations.tsx`, `quotation-detail.tsx`: pass it.
  - `src/mocks/data/quotations.ts`: sets it.
- **A quotation's order (BE-019)**
  - `src/features/orders/api/orders.schemas.ts`, `orders.api.ts`, `hooks/use-order-list-params.ts`: `quotationId`.
  - `components/place-order.tsx`: one filtered call.
  - `src/mocks/handlers/orders.ts`: the filter.
- **Records**
  - `Docs/Plan.md` §9.
  - `Docs/Tested-Features.md`.
  - `../docs/Backend-Tasks.md`: BE-019 ticked.

## Tests

- **`src/features/leads/components/leads-ui.test.tsx`**
  - `[LEAD-001]` sorting by customer from page 2:
    - it returns to page 1 and sends `sort=farmer_name&order=asc` with no cursor;
    - the rows come back in order;
    - Value then takes over the sort.
  - `[LEAD-002]` the New lead picker searches with `levels` and never offers the state. This test fails when the picker is given `levels={null}`.
- **`src/features/lookups/api/lookups.test.ts`** `[MSTR-002]`
  - The levels filter.
  - `levels` is sent comma-separated and never with `level`.
- **`src/features/leads/lib/timeline-entries.test.ts`**
  - `[LEAD-005]` names read beside the ids; a blank name is no name.
  - `[LEAD-008] assignmentSentence`: new owner and partner, a handover, an unassigned owner, events without names.
- **`src/features/leads/components/lead-assign.test.tsx`** `[LEAD-008]`: after assigning, the history names the new owner, the previous one and the partner.
- **`src/features/quotations/components/quotations-ui.test.tsx`** `[QUOT-001]`: a waiting draft reads "Awaiting approval", and other drafts still read "Draft".
- **`src/features/quotations/api/quotations.test.ts`** `[QUOT-001]`
  - The flag is read for every draft.
  - A row without it reads as not waiting.
- **`src/features/orders/api/orders.test.ts`** `[SO-001]`
  - `quotation_id` is sent.
  - The carrying order is found.
  - A free quotation finds none.
- **`src/features/orders/components/orders-ui.test.tsx`**: "Open order" on an ordered quotation, now through the filter.
