---
date: 2026-10-12
type: fix
title: Go-live fixes from the 10 Oct staging walk
dataIds:
  - APP-006
  - APP-003
  - LEAD-003
  - LEAD-005
  - LEAD-008
  - LEAD-013
  - LEAD-014
  - APPR-001
  - APPR-002
  - QUOT-002
  - SO-002
  - CMPL-003
  - AUTH-001
author: Nakul Srivastava
breaking: false
---

## Before

The 10 Oct staging walk of leads, quotations and orders (handovers `walk-fixes-10-oct.md` and `walk-fixes-10-oct-whatsapp-history-approvals.md`, "Yours (frontend)") found these on the frontend. The backend side of each was already done.

- **F-1:** a dealer saw the lead score, the duplicates box and the "Possible duplicates" button.
- **F-8:** a dealer could open `/approval-limits`, `/qr-codes` and `/dispatch` by typing the address. The empty approval limits said "Ask the backend team to seed them".
- **F-9:** the channel-partner box held "No channel partner" as text, so typing searched `q=No channel partnerBhavesh`.
- **F-11:** a step nobody of its role could decide still read "Waiting now" on an order's or refund's trail, and "Waiting for a District Manager…" on a quotation.
- **F-13:** the first click on a page that had just opened was lost on `/tasks`, `/leads`, the lead page and `/approvals`; the next Approve after a decision took several clicks.
- **F-14:** "Preparing the PDF" stayed after Send until a reload when the tab was in the background.
- **F-16:** the timeline said "merged another lead", "Asha Patel flagged 6 possible duplicates", "Quotation discount approved Draft", "the customer · Quotation opened by the customer", and gave a discount decision two lines.
- **F-17:** access-denied pages showed "REF TASK-001 · <uuid>" under the page's own header and filters.
- **F-19:** "by SMS" on the dealer sign-in; the QR code's internal label and "Loading…" on the farmer's enquiry form; an em dash on QR codes; "Your territory at a glance" for the admin and MD; quotation-only copy on orders typed in directly; "10.00 defective of 100.00 NOS"; no confirmation before a complaint submit, which messages the contact; the Reason box red as soon as its list opened.
- **Changed responses:** the score is now a whole number sent as `"28.00"`; an assign that changes the partner re-prices the lead's drafts; leads take land in hectares (FS-052).

## Now

- **Route guards (APP-006, F-8).** A page whose menu item the user can't see can't be opened by its address either: the shell shows "You don't have access to this page" with **Back to the dashboard**, and the top bar says "Polysil CRM" instead of the page's title. The page itself, its header, filters and skeleton are never drawn. One rule, the nav's, covers every page; `/leads/duplicates` is staff only too. Approval limits is now a staff-only menu item, as its endpoint is.
- **No reference on a 403 (F-17).** Nothing failed, so `ErrorState` shows no "Ref" for a 403 anywhere.
- **Dealers (F-1, F-8).** No score, no possible-duplicates notice and no "Possible duplicates" button for a partner user. On QR codes, New QR code, Edit and Switch off are staff only, even if the page is opened.
- **Approval limits, empty:** "No approval limits are set." and why it matters, nothing more.
- **Channel partner box (F-9).** "No channel partner" (and "Unassigned" for the owner) is the placeholder; typing starts a fresh search. Choosing nobody empties the box.
- **Stalled steps (F-11).** The step waiting now reads "No District Manager to decide. With the next manager up." on an order's trail, a complaint refund's trail and a quotation's discount notice.
- **First click (F-13).** Only the page being left animates now: it slides and fades out over the new page, which takes clicks at once. The approval decision dialog closes as soon as the decision is saved (the toast confirms it), so the next row takes the next click.
- **PDF (F-14).** The quotation, order and customer-link pages keep checking while the tab is in the background.
- **Timeline (F-16).**
  - "Asha Patel merged POL/GJ/2026-27/00094 into this lead", each number a link.
  - "6 possible duplicates found: 00083, 00088, …", with no person's name: the system found them.
  - "Asha Patel marked 00083 as not a duplicate."
  - "The customer opened QT/…", on the lead and as "Opened by the customer" alone on the quotation.
  - A draft is "draft quotation v1" or "draft order".
  - A discount decision is one line, on the lead and on the quotation's history.
- **Copy (F-19).** "a 6-digit code is on its way on WhatsApp"; no QR label and no "Loading…" before a state on the enquiry form; no em dash on QR codes; the dashboard reads "Leads, quotations, orders and service at a glance."; delivery, delete and cancel dialogs on a direct order don't mention quotations; "10 defective of 100 NOS".
- **Complaint submit (F-19, F-3).** Submit asks first: "Submit for the manager's check?", naming the contact and their mobile, who "gets a WhatsApp at each step, once messages are switched on". A refusal stays in the dialog. The form's hint says the same.
- **Reason box (F-19).** A list field no longer turns red when its list opens; only when it is closed or left without a choice, or on submit. This is the shared `LookupSelect`, so the lost reason and every other admin list behave the same.
- **Leads.** The score is a whole number. A partner change refreshes the quotations, so a draft shows its new prices. The New lead and Edit forms ask for land in hectares and send `land_hectares`; the lead page shows "1.8 hectares (4.45 acres)".
- **Theme (F-20).** Checked by eye: with the computer in dark mode, choosing Light gives a light page.
- **Checked** on a phone in dark mode and a desktop in light mode, as a dealer and as staff. axe found nothing.

## Discussion

- **F-13's cause.** Reproduced in Chromium: going to Tasks from the menu and clicking New task as soon as it showed sent the click to `<main>` every time. The arriving page was captured into the view transition, and Chrome doesn't hit-test a captured element until the transition ends (about 350 to 500 ms). `::view-transition { pointer-events: none }` was already set, and doesn't help with this. Animating only the leaving page keeps the direction cue and never captures the page people are about to use. The rejected option was skipping the transition on pointer-down: the click is already aimed at `<main>` by then. The e2e test `[APP-003] Page transitions` fails on the old code and passes now.
- **The approvals clicks.** In the mock the next row responded once the dialog had gone; the lost clicks landed on the dialog's overlay during the 600 ms it stayed open to show its tick, while the list behind already showed the next row. On staging the wait is longer. The inbox is used many times a day, so the dialog now closes at once.
- **`/qr-codes` for a dealer.** The walk asks for a route guard; the backend note describes a read-only dealer view. The page isn't in a dealer's menu, so the guard applies, and the page also hides its writes from partners. **Open question for the user:** should dealers get QR codes in their menu, read-only?
- **F-19, menus.** A field officer's Assign, QR codes, Dispatch queue and Complaint targets all follow from the role table (RBAC.md §6.1: `leads` V:own CE, `dispatch` V:own, `complaints` V:own CE; the backend lets a field officer set the partner, not the owner, and the dialog says so). Nothing changed; **open question for the user** whether the client wants them out of the menu.
- **F-19, the sixth digit.** The enquiry form and the dealer sign-in already submit on the sixth digit; unchanged.
- **F-12** (no files on a complaint after the QC verdict) is the backend's rule; **open question for the user** to confirm with the client. Nothing changed.
- **Not done here:** a "Deleted leads" view (`deleted=true`, optional in the handover), and the mock's quotation pricing for products added in Products & prices (mock-only polish). Both stay in the handover's §10.
- **Land.** The backend stores hectares and returns acres beside them (FS-052). A lead with only acres keeps them: the edit form sends land only when it changes.
- **`EmptyState` and `EmptyTitle` take a `level`** (2 or 3, default 3), as `CardTitle` does, so a page-sized empty state (access denied, not found) sits under the top bar's h1 without skipping a level.

## Files changed

- `src/components/layout/`: `route-guard.tsx` (new), `app-shell.tsx`, `app-header.tsx`, `navigation.ts` (`canOpenPath`, Approval limits staff only, dashboard description), `page-transition.tsx`.
- `src/components/patterns/`: `access-denied.tsx` and its story (new), `empty-state.tsx`; `src/components/ui/empty.tsx`; `src/app/(app)/not-found.tsx`.
- `src/lib/api/error-messages.ts`: no reference on a 403. `src/lib/data-ids/registry.ts` and `Docs/Data-IDs.md`: APP-006.
- `src/styles/tokens.css`, `Docs/Design-System.md`: page transitions animate the leaving page only.
- `src/features/leads/`: `lead-detail.tsx`, `leads-toolbar.tsx`, `lead-assign-dialog.tsx`, `lead-timeline.tsx`, `lib/timeline-entries.ts`, `lib/lead-labels.ts` (`formatScore`, `landText`), `lead-fields.tsx`, `new-lead-dialog.tsx`, `lead-edit-dialog.tsx`, `lib/create-lead-errors.ts`, `api/leads.schemas.ts`, `api/leads.mutations.ts`.
- `src/features/orders/`: `api/orders.schemas.ts`, `api/orders.queries.ts`, `components/order-approval.tsx`, `components/order-action-dialog.tsx`, `lib/order-labels.ts`.
- `src/features/quotations/`: `api/quotations.schemas.ts`, `api/quotations.queries.ts`, `lib/quotation-lifecycle.ts`, `components/quotation-history.tsx`.
- `src/features/approvals/components/`: `approval-decision-dialog.tsx`, `approval-limits.tsx`.
- `src/features/complaints/components/`: `complaint-actions.tsx`, `complaint-detail.tsx`, `complaint-form.tsx`.
- `src/features/lead-capture/components/`: `qr-codes.tsx`, `enquiry-form.tsx`. `src/features/auth/components/mobile-sign-in.tsx`. `src/features/lookups/components/lookup-select.tsx`. `src/features/session/hooks/use-session.ts` (`useIsStaff`).
- `src/mocks/`: partner users get 403 on QR writes and approval limits, no score, lost reason or duplicates; stalled order steps; inquiry numbers in timeline payloads; land in hectares.
- `e2e/smoke.spec.ts`; `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/Frontend-Handover.md` §10; `Docs/screenshots/go-live-fixes/`.

## Tests

- `components/layout/route-guard.test.tsx` (new): a dealer at each guarded page gets access denied, no Ref; admin and dealer pages render.
- `components/layout/navigation.test.ts`: `canOpenPath` for dealers, staff with and without the permission, and pages outside the nav.
- `lib/api/url-and-errors.test.ts`: a 403 has no reference, a 500 keeps one.
- `features/leads/`: `lead-activity.test.tsx` (the F-16 sentences, one line per discount decision; a whole score for staff; no score or duplicates for a dealer), `lead-assign.test.tsx` (the placeholder and a clean search; the quotations refresh), `lead-stage.test.tsx` (the Reason isn't red when its list opens; fails without the fix), `lib/timeline-entries.test.ts`, `lib/lead-labels.test.ts`, `api/leads.test.ts`, `leads-ui.test.tsx` (hectares).
- `features/orders/components/orders-ui.test.tsx`: the stalled step on the trail. `features/quotations/lib/quotation-lifecycle.test.ts`: the stalled discount notice, one history line per decision. `features/quotations/api/quotations.queries.test.ts` (new): the PDF polls run in the background.
- `features/approvals/`: the dialog closes at once after a decision; "No approval limits are set." with no ask of the backend team.
- `features/complaints/components/complaints-ui.test.tsx`: submit asks first, and a refusal shows in the dialog. `features/lead-capture/components/lead-capture-ui.test.tsx`: QR codes read-only for a dealer; no label and no "Loading…" on the enquiry form. `features/auth/components/mobile-sign-in.test.tsx`: WhatsApp, not SMS.
- `e2e/smoke.spec.ts` `[APP-003] Page transitions`: a click on New task the moment it appears opens the dialog (fails on the old transition).
- **By hand,** in Chromium on the mock: as a dealer (partner sign-in) on every guarded page, the menu and a lead; as staff, a lead, Assign, Mark as lost, a merged lead's and a duplicate's timeline, a stalled order, a complaint submit, the theme and the enquiry form. Desktop light and phone dark; axe found nothing. Not yet checked on staging.
