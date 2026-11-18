---
date: 2026-10-18
type: feature
title: The customer record
dataIds:
  - LEAD-016
  - LEAD-017
  - LEAD-018
author: Nakul Srivastava
breaking: false
---

## Before

Each lead stood alone. Someone who enquired twice had two unrelated leads, and nothing showed their quotations and orders together. The lead's "At a glance" listed other leads on the same mobile, but never as one customer.

## Now

Built to `customer-record.md` (FS-041). A lead that reaches qualified gets a customer, found by mobile or made new; later leads from that number join it. A user sees a customer when they can see one of its leads.

**Customers** (`/customers`, LEAD-016)

- A **Customers** tab in Sales, after Leads, and a menu item for everyone with `leads.view`.
- **Find a customer** by name or mobile. The search starts at three letters or digits; below that the page says so and keeps the full list.
- An **Area** filter, using the territory picker.
- Each card shows the name, mobile, village or area, type, lead count, and **Consent** once it is given. Newest first, 50 at a time, with **Show more**.
- Loading skeletons, an empty state (none yet, or no match with what to try), and an error with a retry.

**A customer's page** (`/customers/{id}`, LEAD-017)

- The name with its type and **Consent given** or **No consent**, then the mobile, area and lead count.
- **Leads**: each lead's number, source, campaign, date and stage.
- **Quotations** and **Orders**: number, total, the lead it is on, when it was sent or submitted, and its status.
- **Details**: mobile, email, area, village, address, survey number, consent (when, and how it was given) and the customer-since date.
- **Timeline**: everything on the customer's leads, newest first. Each lead entry reads as on the lead's own timeline and names its lead with a link. The customer's own entries read "Became a customer", "Asha Patel recorded the customer's consent", and so on. Older entries come with **Show older**.
- A customer the user can't see opens the not-found page.

**Correcting it** (LEAD-018, staff with `leads.edit`; hidden from dealers)

- **Edit**: type, name, email, area, village, survey number and address. Only what changed is sent. The mobile is the customer's identity and isn't offered. The name must be filled in and the email must look like one; the backend's refusals land on their fields.
- **Record consent** asks how it was given (on WhatsApp, on a form, spoken, in writing). **Withdraw consent** confirms first. Both go on the timeline.

**On a lead**

- A **Customer** line with **Open the customer** once the lead has one.

**Mock**

- One customer per mobile among qualified, quoted, negotiation and won leads; the first has consent.
- Search by name or mobile digits, and by area through its lineage.
- The page and timeline cover only the leads the role can see.
- PATCH refuses a dealer and wants the channel with consent.

Walked as Admin on a desktop in light mode and a 390 px phone in dark mode: search, the page, Edit, consent recorded, and the lead's link. Axe found nothing, with no console errors and no sideways scroll.

## Discussion

- **"Became a customer" has no name.** The backend makes the customer, so the entry has no actor. "Polysil became a customer" would read as if Polysil were the customer.
- **A consent switch, as two buttons.** The contract asks for a consent switch. Recording consent needs the channel, so it opens a short form; withdrawing it asks first. A bare toggle couldn't ask for either.
- **The lead's "At a glance" still says "same mobile".** It is RPT-003's own summary, and its wording stays until the report contract says otherwise.

## Files changed

- `src/features/customers/api/customers.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: new, the contract, the four calls, the list, page and timeline queries, and the edit mutation.
- `src/features/customers/lib/customer-labels.ts`: new, the type and consent channel labels.
- `src/features/customers/components/customers-search.tsx`: new, the search page.
- `src/features/customers/components/customer-detail.tsx`: new, the page, its cards and timeline.
- `src/features/customers/components/customer-edit-dialog.tsx`: new, Edit (`draftOf`, `patchOf`, `draftProblems`).
- `src/features/customers/components/consent-dialog.tsx`: new, record or withdraw consent.
- `src/app/(app)/(sales)/customers/page.tsx`, `src/app/(app)/(sales)/customers/[customerId]/page.tsx`: new routes.
- `src/features/leads/api/leads.schemas.ts`: `customer_id` on a lead.
- `src/features/leads/components/lead-detail.tsx`: the Customer line.
- `src/features/leads/components/lead-timeline.tsx`: `TimelineItem` exported, with an optional `on` that names the lead.
- `src/features/leads/components/sales-tabs.tsx`, `src/components/layout/navigation.ts`: the Customers tab and menu item.
- Mock: `src/mocks/data/customers.ts`, `src/mocks/handlers/customers.ts` (new), `src/mocks/db.ts`, `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-016, LEAD-017, LEAD-018.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/customers/`.

## Tests

`src/features/customers/components/customers.test.tsx`, 10 tests:

- `[LEAD-016] Customers search (contract)`:
  - newest first, and a short search ignored;
  - by name, mobile digits and area, and no match.
- `[LEAD-017] Customer record (contract)`:
  - leads, documents and a timeline that names each lead;
  - 404, and `customer_id` on a qualified lead but not a new one.
- `[LEAD-018] Editing a customer and consent (contract)`:
  - a dealer refused, the channel required, consent recorded then withdrawn, both on the timeline;
  - only changes sent, and the name and email checks.
- `[LEAD-016] CustomersSearch`: the list, the three-character hint, no match, then a match by mobile.
- `[LEAD-017] CustomerDetail`:
  - the cards and timeline, then consent recorded;
  - the village corrected through Edit;
  - a dealer sees the customer of their lead without Edit or consent.

`src/components/layout/navigation.test.ts`: a leads-only user now also gets **Customers**.

To check by hand in the mock as Admin:

1. Open Sales → Customers and search by part of a name.
2. Open a customer, record consent as Spoken, and see it on the timeline.
3. Edit the village.
4. Open one of its leads and follow **Open the customer** back.
