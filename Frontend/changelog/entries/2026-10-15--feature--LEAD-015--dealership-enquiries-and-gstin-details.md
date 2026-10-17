---
date: 2026-10-15
type: feature
title: Dealership enquiries, and a partner's names from the GST record
dataIds:
  - LEAD-015
  - CHNL-006
author: Nakul Srivastava
breaking: false
---

## Before

The backend added two things with FS-053 (`subsidised-orders-and-small-changes.md`):

- **A dealership enquiry type:** `inquiry_type: "dealership"`, for someone asking to become a dealer. Such a lead can be won straight from qualified, without a quotation. The answer that wins it carries `dealer_application`: the application it started and the link to send, or why none was started.
- **GSTIN details:** `GET /gstin/{gstin}` answers the GST record's legal name, trade name, address and status (`lookup: found`) once the server has a provider key, and `unavailable` until then.

The frontend knew three enquiry types, so a dealership lead from the backend would have broken the lead's contract. The channel-partner form asked for every name by hand.

## Now

- **Dealership** is a fourth enquiry type: in the type picker, the lead list's filter and on the lead.
- **A qualified dealership lead offers Mark as won.** The menu says "They're to become a dealer. Closes the lead and starts their dealer application." The dialog says no quotation is needed.
- **Winning it shows Dealer application started,** with the link to send, once:
  - **Copy link**;
  - **Share on WhatsApp**, which opens WhatsApp to the lead's number with a message and the link (nothing is sent by itself).
  - The dialog stays open until Done, even though a won lead has no stage menu.
- **When no application was started,** it says why: the mobile already belongs to a partner (`mobile_in_use`), an application is already open for it (`application_open`), or the number can't take one (`mobile_invalid`).
- **GSTIN details on the partner form,** staff only. Once the GSTIN is complete:
  - **Found:** the legal name, trade name and status, and **Use these details**, which fills the business name (trade name, else legal name), PAN and address and ticks GST-registered. Every field stays editable.
  - **Not found, or no GST provider yet:** says to type the names, as before.
  - **A GSTIN that doesn't check out** says why. Nothing is looked up until the GSTIN is complete, and the answer (it holds a PAN and address) stays out of the logs.
- **The mock:** two qualified dealership leads and a new one; winning one starts an application, or refuses one for a partner's mobile. Two GST records are found; any other GSTIN is `unavailable`, as on the backend today.
- Checked on a desktop in light mode and a phone in dark mode. axe found nothing on the dialogs or the form. It still flags the open stage menu as outside a landmark (moderate); it does the same on any lead, so that predates this change.

## Discussion

- **Use these details, not an automatic fill.** The contract says to prefill the names. One click does that, and doesn't overwrite a name the officer has already typed until they ask. The fields stay editable either way.
- **The public enquiry form keeps three types.** `/public/leads` takes only commercial, subsidised and industrial (`public.md`).
- **The dealer application screens,** and the applicant's own `GET /public/dealer-apply/{token}/gstin/{gstin}`, are part of dealer recruitment, a later plan item. This change only shows the link the win answers with.
- **Not yet checked on staging.** `GET /gstin/{gstin}` answers `unavailable` there until the backend has a provider key (GAP-292).

## Files changed

- `src/features/leads/api/leads.schemas.ts`: `dealership` in `LEAD_INQUIRY_TYPES`; `dealer_application` on a lead, read as `dealerApplication`.
- `src/features/leads/lib/lead-labels.ts`: "Dealership".
- `src/features/leads/lib/lead-lifecycle.ts`: `stageMenuFor` and `stageActionDescription` take the lead's type.
- `src/features/leads/components/lead-stage-menu.tsx`: passes the type; keeps the dialog mounted after the win.
- `src/features/leads/components/lead-stage-dialog.tsx`: Mark as won shows the dealer application.
- `src/features/leads/components/dealer-application-started.tsx`: new, the link with Copy and Share on WhatsApp, or why none was started.
- `src/features/partners/api/partners.schemas.ts`, `partners.api.ts`, `partners.queries.ts`: `gstinLookupSchema`, `lookupGstin`, `gstinLookupQueryOptions`.
- `src/features/partners/components/gstin-details.tsx`: new, the GST record under the GSTIN.
- `src/features/partners/components/partner-form.tsx`: shows it, staff only.
- `src/mocks/data/leads.ts`, `src/mocks/handlers/leads.ts`, `src/mocks/handlers/partners.ts`: dealership leads and their win; `GET /gstin/:gstin`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-015 and CHNL-006.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/dealership/`: records and screens.

## Tests

- `src/features/leads/lib/lead-lifecycle.test.ts`, `[LEAD-007] stageMenuFor`: a dealership lead is won from qualified; others are not; the won line for each.
- `src/features/leads/components/lead-stage.test.tsx`, `[LEAD-007] LeadStageMenu`:
  - a qualified dealership lead won, its link shown with Copy and a WhatsApp link to the lead's number, then Done;
  - the reason when no application was started.
- `src/features/partners/api/partners.test.ts`, `[CHNL-006] lookupGstin`: a found record read, blank names as null; `unavailable` from the mock; refused to partner users.
- `src/features/partners/components/partners-ui.test.tsx`, `[CHNL-006]`:
  - a found GSTIN shown, then used to fill the name, PAN and address, which stay editable;
  - unavailable and not found ask for the names;
  - no lookup until the GSTIN is complete, and an error says to type the names.
- Walked through in the mock: desktop light and phone dark, as a State Manager (the win) and as Admin (the partner form).
