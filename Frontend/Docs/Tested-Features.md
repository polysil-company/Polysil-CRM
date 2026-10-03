# Tested features — what works, from the user's side

One place to see every feature a user can use today, how far each one is tested, and where it lives. Read it before trying the app by hand: if a story is here with its checks, it has been exercised, and the list of cases tells you what was covered.

**Keep it current.** Update this file in the same pull request that adds or changes a feature, as with [Plan.md §9](Plan.md) — the full list of records is in [AGENTS.md §11](../AGENTS.md). New screenshots go in [`screenshots/`](screenshots), one folder per module, as JPEG at quality 80 (the first ones are WebP).

## How to read it

Each story says who can do what, then the cases that were checked, then how:

| Mark | Means |
| --- | --- |
| 🧪 | **Automated** — unit and component tests (Vitest, Testing Library) against the mock backend, which follows the backend's contract. Run with `npm test`. |
| 🌐 | **End to end** — the Playwright smoke suite, on desktop and phone, with axe accessibility checks. Runs in CI. |
| 👀 | **Walked through** — clicked through in a real browser against the mock backend, at 360px and on desktop, light and dark, with screenshots. |
| 🔌 | **Real backend** — checked by hand against the backend's dev API. **Only the stories marked 🔌 have been.** Everything else still needs this before staging ([Plan.md §9.1](Plan.md)). |

**Showing it to the client:** [Demo-Guide.md](Demo-Guide.md) lists what's ready in plain words, and walks through the demo click by click.

**Testing on the real backend:** [Live-Test-Plan.md](Live-Test-Plan.md) is the plan, case by case and role by role, for checking the hosted app against the dev API. It also produces a client walkthrough and an issue report.

**Where it is:** `integration` means merged. `PR #n` means built and passing locally but still in review. A story in an open PR is not on `integration` yet.

## At a glance

| Module | Stories | Tested | Where |
| --- | --- | --- | --- |
| [Sign-in and session](#sign-in-and-session) | 4 | 🧪 🌐 🔌 | `integration` |
| [App shell](#app-shell) | 3 | 🧪 🌐 | `integration` |
| [Leads — list, create, open](#leads--list-create-open) | 4 | 🧪 🌐 🔌 | `integration`; sorting and territory levels in PR #42 |
| [Leads — history, notes, stage, assign](#leads--history-notes-stage-assign) | 4 | 🧪 👀 | `integration` |
| [Quotations — reading](#quotations--reading) | 4 | 🧪 👀 | `integration` |
| [Quotations — the builder](#quotations--the-builder) | 5 | 🧪 👀 | `integration` |
| [Quotations — send, approve, answer, revise, delete](#quotations--send-approve-answer-revise-delete) | 7 | 🧪 👀 | `integration` |
| [Quotations — the customer's link](#quotations--the-customers-link) | 2 | 🧪 🌐 👀 | `integration` |
| [Approvals](#approvals) | 5 | 🧪 🌐 👀 | `integration`; limits in PR #35 |
| [Sales orders and dispatch](#sales-orders-and-dispatch) | 7 | 🧪 🌐 👀 | PR #34 |
| [Dashboard, notifications, messages](#dashboard-notifications-messages) | 3 | 🧪 🌐 👀 | dashboard on the backend's contract in PR #41; bell and messages connected in PR #43 |

Roles in the mock are switched from the account menu ("Preview as role"). The demo sign-in is `asha@polysil.in` / `polysil-demo`; partners use the code `123456`.

---

## Sign-in and session

Details and tests: [changelog entry](../changelog/entries/2026-09-15--feature--AUTH-001--sign-in-sessions-and-permissions.md). 🔌 here means signing in as staff on the dev API, as part of the leads check below.

- **AUTH-003 · Staff sign in with work email and password.** Show-password toggle, Caps Lock warning; a wrong password clears only the password; a locked account says so. 🧪 🌐 🔌
- **AUTH-001 · A channel partner signs in with a one-time code** sent to their mobile, typed any common way. The screen never claims a code was sent to an unknown number. 🧪 🌐
- **AUTH-004 · Staying signed in.** The session renews itself before it expires, when the tab comes back and when the connection returns; a reload keeps you signed in. 🧪 🌐
- **AUTH-005, AUTH-006 · Signing out, or a session the backend ends,** clears everything and opens sign-in in every tab; after an expiry you return to the page you were on. A signed-out visitor sent to a page lands back on it after signing in. 🧪 🌐

## App shell

Details and tests: [foundation](../changelog/entries/2026-09-14--feature--APP-001--frontend-foundation.md), [sidebar and titles](../changelog/entries/2026-09-15--feature--APP-005--collapsible-sidebar-and-page-titles-in-the-top-bar.md).

- **APP-001 · Navigation follows permissions.** The sidebar, command menu, sales tabs and "New lead" show only what the role may use. 🧪 🌐
- **APP-005 · The sidebar collapses** to an icon rail on desktop (Ctrl/⌘ + B); the page title and description sit in the top bar. 🧪
- **APP-001 · Command menu** opens and closes from the keyboard; light and dark themes. 🧪 🌐

## Leads — list, create, open

Details and tests: [leads on the dev API](../changelog/entries/2026-09-22--api-integration--LEAD-001--leads-on-the-dev-api.md). Checked by hand on the dev API as admin, Asha and Ravi, each seeing their own total.

- **LEAD-001 · Browse leads,** newest first, or filtered by stage, with each stage explained in the filter (PR #45, [screen](screenshots/stage-help/stage-filter-desktop-light.jpg)), sorted by customer or value from the column headers (BE-001; changing the sort starts again from page 1, since a page link belongs to one order) (PR #42: 🧪 👀, [screen](screenshots/backend-pickups/leads-sorted-by-customer-desktop-light.jpg)). Pages forward and back with the page in the URL (refresh and shared links land on the same page); filter by several stages, one source, one type; search by name, part of the mobile, or the exact inquiry number; "1–25 of 74", or "1,000+" when the backend stops counting. States: skeleton, empty, nothing matches, a page link that no longer works, an emptied page, server error, a broken row left out instead of blanking the page. 🧪 🌐 🔌
- **LEAD-001 · Filter by area** (backend #50, PR #PRNUM; screens: [districts](screenshots/area-filter/area-districts-desktop-light.jpg), [talukas in Rajkot](screenshots/area-filter/area-talukas-desktop-light.jpg), [filtered list](screenshots/area-filter/leads-filtered-by-rajkot-desktop-light.jpg), [phone, dark](screenshots/area-filter/area-districts-phone-dark.jpg)): the Area pill lists the districts that hold a lead you can see, each with how many — with one state, it starts at its districts. Tick several (up to 20; the rest are disabled with a note) or open a district to tick its talukas; a district takes in every taluka and village under it, and its count matches the filtered list. "All districts" goes back. The choice is in the URL (`?area=`), the pill names the area picked, and Clear or Reset filters removes it. States: loading, "no lead filed under a taluka — choose the district itself", an error with Try again. 🧪 👀
- **LEAD-002 · Create a lead.** Territory picker (districts on open, any district, taluka or village by typing; never the state, which a lead may not sit in: BE-005, PR #42, [screen](screenshots/backend-pickups/new-lead-no-state-desktop-light.jpg)), lookups from the administrators' lists, crops (up to 10, from `GET /lookups/crops`) and land in acres, a safe retry that never creates two leads, field errors on their fields. Dropdowns are not marked wrong just for being opened; they are checked on submit. A flagged duplicate is named in the toast, and several are counted ("3 possible duplicates (A, B and C)"), as on the lead page. 🧪 🔌 (crops, land and the duplicate count 🧪 👀 only)
- **LEAD-003 · Open a lead.** The real record: stage and priority (hot, warm or cold only while the lead is open), contact, territory, owner and office or "Unassigned", partner, score, crops (a switched-off crop greyed) and land, dates, the lost reason, a merged lead pointing to the lead it went into, possible duplicates with how they matched. No win probability or engagement cards (BE-004). The list shows crops and every value in whole rupees. 🧪 🌐 🔌 (crops and land 🧪 👀 only)
- **LEAD-004 · The lead count** in the sidebar and Sales tab is exact (`GET /leads/stats`), never capped. 🧪

## Leads — history, notes, stage, assign

Details and tests: [changelog entry](../changelog/entries/2026-09-27--feature--LEAD-005--lead-timeline-and-notes.md). Screens: [lost lead with its history](screenshots/leads/lead-lost-activity-desktop-light.webp) ([dark](screenshots/leads/lead-lost-activity-desktop-dark.webp), [phone](screenshots/leads/lead-activity-phone-light.webp)), [stage menu](screenshots/leads/lead-stage-menu.webp), [mark as lost](screenshots/leads/lead-mark-lost-dialog.webp), [assign](screenshots/leads/lead-assign-dialog.webp), [phone header, dark](screenshots/leads/lead-header-phone-dark.webp).

- **LEAD-005 · Read a lead's history** as sentences ("Ravi Joshi moved the lead from Qualified to Lost", with the reason and note), newest first, 20 at a time with "Show older activity". Covers notes, stage changes, reopenings, assignments, edits, merges, duplicate flags, quotation events with the quotation's number as a link ("QT/GJ/2026-27/00009 · v2"), approval steps ("approved the District Manager step"), and order and dispatch events with the dispatch number. An order's own number and link wait on BE-020. An unknown kind still reads well. States: skeleton, "No activity yet", error with retry, an older page failing without losing what is shown. 🧪 👀
- **LEAD-006 · Add a note** (anyone with `leads.edit`, not on a merged lead). Ctrl/⌘ + Enter saves, Enter adds a line; the note appears at the top at once; a counter near the 2,000-character limit; a failed save keeps the text, and a retry never adds it twice. 🧪 👀
- **LEAD-007 · Move the stage.** Update stage says what the current stage means, and what each move does (PR #45, [screen](screenshots/stage-help/stage-menu-phone-dark.jpg)). It offers only the moves allowed from the current stage: Contacted and Qualified in one click; Lost needs a reason (note optional); Won confirms; a lost lead can be reopened. Steps that happen on a quotation are listed but disabled with where they happen. If someone else moved the lead first, it says so and shows the latest; Won without an accepted quotation is explained. No menu on a won, merged or dormant lead, or without `leads.edit`. 🧪 👀
- **LEAD-008 · Assign the owner and channel partner** on an open lead (the history names them: "assigned the lead to Ravi Joshi and made Khodiyar Irrigation the channel partner", or "handed the lead from Asha Mehta to Ravi Joshi"; BE-006, PR #42, [screen](screenshots/backend-pickups/lead-history-assignment-desktop-light.jpg)): the people you may assign (or "Unassigned"), partners in your area by name, code or contact person (backend #49, PR #PRNUM). Only what changed is sent; an employee is told only a manager can change the owner; a refused partner shows on its field; no Assign on a closed lead. 🧪 👀

## Quotations — reading

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--QUOT-001--quotations-list-and-detail.md). Screens: [list](screenshots/quotations/quotations-list.webp), [a quotation in negotiation](screenshots/quotations/quotation-detail-negotiation.webp), [on a phone](screenshots/quotations/quotation-detail-phone.webp), [a lead's quotations](screenshots/quotations/lead-quotations-card.webp). These were captured before the action bar (PR #22) was added.

- **QUOT-001 · Browse quotations** newest first: number (or Draft), version, lead, party, a labelled status chip, type, owner, dates, total. A draft whose discount waits for a manager reads "Awaiting approval", here, on the lead's card and on the quotation (PR #42, [desktop](screenshots/backend-pickups/quotations-awaiting-approval-desktop-light.jpg), [phone, dark](screenshots/backend-pickups/quotations-awaiting-approval-phone-dark.jpg)). Search by number, name or mobile; several statuses at once; one sales type; "Show older versions" marks replaced ones "Superseded by v2". Filters and page in the URL. States as on the lead list. 🧪 👀
- **QUOT-002 · Read a quotation** exactly as the backend prints it — the screen never adds up a figure. Notices, most important first: replaced by a newer version (with a link), indicative pricing, the customer's decision, the PDF preparing (the page checks again by itself) or failed, and the backend's warnings. Items in the client's columns (three discount tiers, taxable value, GST as CGST + SGST or IGST, total), cards on a phone; totals; party, terms, details and the customer link with Copy. A quotation outside your scope is "not found". 🧪 👀
- **QUOT-003 · Open the PDF** in a new tab from a ten-minute link, never fetched with the sign-in token. A pop-up blocker gets a toast with the link; "Preparing PDF…" while it renders; a refusal says why. 🧪 👀
- **QUOT-001 · A lead's quotations** — a card on the lead page listing every version, the older ones muted. 🧪 👀

## Quotations — the builder

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--QUOT-004--quotations-make-and-edit-a-draft-priced-live.md). Screens: [priced items](screenshots/quotations/builder-priced-desktop.webp), [dark](screenshots/quotations/builder-desktop-dark.webp), [phone](screenshots/quotations/builder-phone-light.webp), [the saved draft](screenshots/quotations/builder-saved-draft.webp). Walked through: two items (a pipe with 10% + 5%, an HDPE lateral on a stand-in rate), totals ₹25,485.01, saved, the draft showing the same figures. The figures on one line were checked by hand.

- **QUOT-004 · Start a quotation from a lead** with New quotation (for those who may create). A lead that can't be quoted says why: "Qualify the lead first", "Reopen the lead first", dormant, merged. No lead given: "Start from a lead". 🧪 👀
- **MSTR-003 · Pick products** by typing: searched on the server, each option naming its unit, HSN and code; the quantity shows the unit. 🧪 👀
- **QUOT-005 · See prices as you type.** When typing pauses, the whole basket is priced by the backend: rate, taxable value, GST split as the backend split it, total, "Indicative rate" on stand-ins; old figures stay dimmed while new ones come. A row says what it still needs ("Choose a product", "Enter a quantity above 0", "Discounts are percentages from 0 to 100"). 🧪 👀
- **QUOT-004 · Save the draft.** Save stays off until every item is complete and priced, and says why. A double click or retry never makes two drafts. Customer and terms are validated (Indian mobile, GSTIN format) in the browser and by the backend, whose field errors land on the right field or item. If prices changed since you priced them: "Prices changed since you priced this", the items show the new rate, the basket re-prices, and the next save goes through. 🧪 👀
- **QUOT-004 · Edit a draft** from its page; only a changed header is sent. A sent quotation can't be edited — the page says to revise it. 🧪 👀

## Quotations — send, approve, answer, revise, delete

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--QUOT-006--quotations-send-discount-approval-the-customer-s-answer.md). Walked through in one run as Admin: ask for approval → approved → send → PDF ready → negotiation → revise → delete, with no page errors. Screens: [needs approval](screenshots/quotations/draft-needs-approval.webp), [waiting](screenshots/quotations/draft-waiting-for-approval.webp), [send dialog](screenshots/quotations/send-dialog.webp), [sent, in negotiation](screenshots/quotations/sent-in-negotiation.webp), [answer dialog](screenshots/quotations/answer-dialog-desktop-dark.webp) ([phone](screenshots/quotations/answer-dialog-phone.webp)), [version 2 draft](screenshots/quotations/revision-v2-draft.webp), [history and versions](screenshots/quotations/history-and-versions-desktop-dark.webp) ([phone](screenshots/quotations/history-phone-light.webp)), [back on the lead after deleting](screenshots/quotations/lead-after-draft-deleted.webp).

- **QUOT-006 · Send a quotation** within the owner's discount limit: on WhatsApp to the party's mobile (once the PDF is ready), or without a message to share the link by hand. It gets its number and 45 days' validity, and a qualified lead moves to Quoted; "Preparing PDF…" then Open PDF. Refusals: no items, prices changed since the save (with "Open the draft"), the lead closed. 🧪 👀
- **QUOT-007 · Ask for discount approval** when the discount is above the limit: the notice shows the discount and the limit, and the request takes a reason. Then "Waiting for a State Manager to approve…" with Send off (the page checks every 30 seconds), "Discount approved" with Send, "refused" with the approver's remark, or "no longer applies" after the figures changed. The builder warns that saving withdraws a waiting request. No manager's limit covers it: lower the discount. The request waits in the manager's [Approvals](#approvals) inbox. 🧪 👀
- **QUOT-008 · Record the customer's answer** on a sent, viewed or negotiating quotation: Accepted (the lead is Won), In negotiation (the lead moves to Negotiation), Rejected (the lead stays), each with what the customer said. Nothing to answer past the validity date, on an accepted or a replaced version. 🧪 👀
- **QUOT-009 · Revise** a sent, viewed, negotiating, rejected or expired quotation into the next version, a draft at today's prices, and open it; one open revision at a time; sending it marks the old one replaced, and it keeps the same number. **Versions** lists them all. 🧪 👀
- **QUOT-010 · Read a quotation's history**: drafted, edited, sent (how), opened (how often), the answer with its remark, revised, and each step of the discount approval; older events a page at a time. The lead's history names the same events. 🧪 👀
- **QUOT-011 · Delete a draft** (only roles holding `quotations.delete` — Admin in the mock) and return to the lead. A sent quotation is never deleted; a State Manager sees no Delete. 🧪 👀
- **QUOT-006 … 011 · When someone else got there first** (sent it, answered it, revised it), the dialog closes, a toast says what happened, and the page shows the latest. 🧪

## Quotations — the customer's link

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--QUOT-012--quotations-the-customer-s-page-for-a-shared-link.md). Screens: [phone](screenshots/public/shared-quotation-phone-light.webp), [desktop, dark](screenshots/public/shared-quotation-desktop-dark.webp), [unknown link](screenshots/public/unknown-link-phone-light.webp) ([dark](screenshots/public/unknown-link-desktop-dark.webp)).

- **QUOT-012 · A customer opens their link** (`/q/…`) without signing in: the number, who it's from, the total including GST, the items count, when it was sent and until when it's valid, and **View quotation** opening the PDF in a new tab. The PDF opens only when tapped, so a WhatsApp preview is never counted as a view. While the PDF is made: "Preparing the PDF…", checked again by itself. Expired or replaced quotations still open, with a note. Nothing personal is shown, and the link's secret isn't passed on to the PDF's host. 🧪 🌐 👀
- **QUOT-012 · A wrong or cut-off link** says "This link doesn't open a quotation", with what to do. 🧪 👀

## Approvals

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--APPR-001--approvals-inbox.md). Walked through as a State Manager: 7 requests; a rejection without a reason refused, then rejected with one; a quotation discount approved; lower steps added; on a phone in dark mode; an Employee sees no Approvals. Screens: [the inbox](screenshots/approvals/inbox-state-manager-desktop-light.jpg), [a reason to reject](screenshots/approvals/reject-needs-a-reason-desktop-light.jpg), [with steps below](screenshots/approvals/inbox-including-steps-below-desktop-light.jpg), [phone, dark](screenshots/approvals/inbox-phone-dark.jpg), [approve on a phone](screenshots/approvals/approve-dialog-phone-dark.jpg).

- **APPR-001 · See what waits on me** (whoever holds `sales_orders.approve` or `quotations.approve`: managers, Accounts, Dispatch): quotation discounts and sales orders side by side, oldest first — what it is, its number (or "Draft quotation"), the party, the total, the discount asked, stand-in pricing, who raised it and when, how long it has waited, and "Open the quotation" or "Open the order". An order's steps come one at a time: the next joins its inbox when the one before is approved. Accounts and Dispatch see only their own steps. A count in the sidebar (with a dot on the collapsed rail); the inbox and the count check every minute. States: skeleton, "Nothing waits on you", an error, a later page failing without losing what is shown. 🧪 🌐 👀
- **APPR-001 · Cover for a manager on leave:** "Include steps below me" (kept in the URL) adds lower managers' steps, each marked whose it is. A step nobody of its role covers always shows, marked "No District Manager to decide". 🧪 👀
- **APPR-001 · Approve or reject.** Rejecting needs a reason, which the person who asked reads; approving takes one optionally — except at Accounts, where every decision needs a remark (BE-018). The request leaves the inbox and the count drops; an approved quotation discount turns the officer's button into Send, a rejected one shows the reason on the draft. 🧪 🌐 👀
- **APPR-001 · Read why they asked** (backend #49, PR #PRNUM; screens: [the inbox](screenshots/approvals/inbox-with-reason-desktop-light.jpg), [the dialog](screenshots/approvals/decision-dialog-with-reason-desktop-light.jpg)): the remark the salesperson wrote when asking for discount approval shows under the row, and again at the top of the decision dialog ("Asha Mehta's reason: …"). Requests raised without one show nothing extra. 🧪 👀
- **APPR-002 · Approval limits** (Admin → Approval limits): the order-value ladder (District, State, Regional, including GST) the discount ladder (the field officer's own limit up to Admin-Sales), the refund ladder for complaints (District, State, Regional in rupees, then Accounts; PR #46), and a territory's own limits. A limit for a document the screen doesn't know yet is left out instead of failing the page (it failed on the dev API when refund limits arrived). An administrator (`masters.edit`) changes one level: the dialog gives the bounds in words, offers "No limit" only at the top, refuses a limit out of order on the field, and shows the new ladder at once; if another level changed meanwhile, it says so and reloads. Everyone else reads them. Screens: [admin](screenshots/approvals/limits-admin-desktop-light.jpg), [out of order](screenshots/approvals/limit-out-of-order-desktop-light.jpg), [changed](screenshots/approvals/limit-changed-desktop-light.jpg), [read-only on a phone, dark](screenshots/approvals/limits-read-only-phone-dark.jpg). 🧪 🌐 👀
- **APPR-001 · When the request moved on** — decided by someone else, withdrawn, or its draft edited after the request — the dialog closes, a toast says which, and the inbox shows the latest. Without the `approvals.approve` permission the rows show, the buttons don't. 🧪

## Sales orders and dispatch

Details and tests: [changelog entry](../changelog/entries/2026-09-30--feature--SO-001--sales-orders-and-dispatch.md). Walked through on the mock backend as a State Manager (list, a returned order edited and submitted again, an order step approved in the inbox), as Dispatch (record with mistakes then correctly, void, close short), and as a field officer on a phone (place an order from an accepted quotation). Screens: [list](screenshots/orders/list-desktop-light.jpg) ([dark](screenshots/orders/list-desktop-dark.jpg), [phone](screenshots/orders/list-phone-light.jpg)), [returned order](screenshots/orders/returned-draft-desktop-light.jpg), [submit](screenshots/orders/submit-dialog-desktop-light.jpg), [waiting on its chain](screenshots/orders/submitted-approval-chain-desktop-light.jpg), [partly dispatched](screenshots/orders/partly-dispatched-desktop-dark.jpg), [record: mistakes](screenshots/orders/record-dispatch-errors-desktop-dark.jpg), [record: filled](screenshots/orders/record-dispatch-filled-desktop-dark.jpg), [dispatched](screenshots/orders/fully-dispatched-desktop-dark.jpg), [voided](screenshots/orders/voided-dispatch-desktop-dark.jpg), [closed short](screenshots/orders/closed-short-desktop-dark.jpg), [place order](screenshots/orders/place-order-dialog-phone-light.jpg), [new draft on a phone](screenshots/orders/new-draft-order-phone-light.jpg), [detail on a phone, dark](screenshots/orders/detail-phone-dark.jpg).

- **SO-001 · Browse orders,** newest first: number (or "Draft order"), dealer or "Direct sale", "Provisional", the party, the status with whom it waits on ("Waiting on Accounts"), how much has shipped (a share and a bar), type, owner, created, total. Filter by several statuses, one type, "Only my orders", and search by number, party or mobile — all kept in the URL. States: skeleton, "No sales orders yet" (orders come from an accepted quotation), nothing matches, a page link that no longer works, an emptied page, errors. 🧪 🌐 👀
- **SO-002 · Open an order:** the lines with ordered, sent, open and short once approved; totals with CGST and SGST or IGST; the approval chain step by step (who decided, when, their remark, "Waiting now", covered by a higher manager); dispatches; party, quotations it came from, delivery, payment terms, place of supply, seller; its history; "Open PDF" once approved ("Preparing PDF…" while it renders, checked again by itself). Notices: returned with the reason, cancelled or closed short with the reason, indicative pricing, no mobile for the confirmation, the PDF failed. 🧪 🌐 👀
- **SO-003 · Place an order** from an accepted, current quotation ("Place order" for roles with `sales_orders.create`): order type (commercial or industrial), delivery address (the party's by default), payment terms, remarks; the draft opens. A quotation already on a live order shows "Open order" instead, found with one `GET /orders?quotation_id=` call (BE-019, PR #42). 🧪 👀
- **SO-003 · Change a draft's delivery, terms and remarks;** delete a draft that was never submitted (holders of `sales_orders.delete` — Admin in the mock); a numbered draft is cancelled instead. 🧪 👀
- **SO-004 · Submit for approval,** or "Submit again" after a return: the order gets its number and waits on its managers by value, then Accounts, then Dispatch. Cancel with a reason — the owner while it is a draft or waiting, a holder of delete once approved, nobody once something has shipped. 🧪 👀
- **DISP-002 · Record a dispatch** (Dispatch, `dispatch.create`): each open item's quantity (or "Everything open"), when it left, challan, invoice, transporter, vehicle. Refused on the field: nothing entered, more than is open, decimals on a whole-unit item, a time in the future. An invoice dated before its challan, or an invoice number already used, is recorded with a warning. The order moves to Partly dispatched or Dispatched. 🧪 👀
- **DISP-002 · Void a dispatch** with a reason — it stays on record, struck through, and its quantities are open again — and **close the rest short** with a reason. Managers see neither. When someone else moved the order first, the dialog closes, a toast says what happened, and the page shows the latest. 🧪 👀

## Dashboard, notifications, messages

The dashboard reads the backend's real shape since the demo-walk fixes ([changelog](../changelog/entries/2026-10-02--fix--RPT-001--demo-walk-fixes.md)). The bell and messages follow the backend's contracts (BE-009, BE-010) since PR #43 ([changelog](../changelog/entries/2026-10-02--api-integration--NOTIF-001--notifications-and-messages-on-the-backend.md)). None of the three has been checked on the dev API by hand yet. Details and tests: [dashboard (foundation)](../changelog/entries/2026-09-14--feature--APP-001--frontend-foundation.md), [notifications and messages](../changelog/entries/2026-09-15--feature--NOTIF-001--notification-bell-and-staff-messages.md).

- **RPT-001 · The dashboard,** read in the backend's own shape (BE-008): open pipeline value, new leads, conversion and overdue follow-ups, each with its change and trend where the backend gives one; the pipeline by stage with value; leads by source; the next follow-ups, marked overdue. Money stays a decimal string until it is printed. Screens: [desktop](screenshots/demo-fixes/dashboard-desktop-light.jpg), [phone, dark](screenshots/demo-fixes/dashboard-phone-dark.jpg). 🧪 🌐 👀
- **NOTIF-001, NOTIF-002 · The notification bell** in the top bar (any signed-in user).
  - The badge counts the unread, checking every 30 seconds with one notification's worth of data.
  - Opening it lists the latest 20, each with its own icon for the backend's 14 kinds; an unknown kind gets the plain bell.
  - A notification opens its lead, quotation or sales order. Tasks and complaints have no screen yet, so theirs only mark read.
  - Mark one or all read: the badge drops at once, is put back if the call fails, then takes the backend's count.
  - States: skeleton, "You're all caught up", an error with retry.
  - Screens: [desktop](screenshots/messages-notifications/notifications-bell-desktop-light.jpg), [phone, dark](screenshots/messages-notifications/notifications-bell-phone-dark.jpg). 🧪 🌐 👀
- **MSG-001 … MSG-005 · Direct messages between staff** (staff only; partners are told messages are for staff), and sharing a lead with a colleague from its page.
  - Conversations, most recent first, with unread counts.
  - The thread, grouped by day. Opening it marks read up to the newest message on screen, so one that arrives meanwhile stays unread.
  - Enter sends, Shift + Enter adds a line; a failed send puts the text back.
  - A lead the sender can't see is refused with a reason.
  - A new conversation keeps its colleague's name until the first message lists it.
  - A colleague who has left: the conversation stays readable and closed. If the backend refuses a send because they have left, the draft stays to copy.
  - Screens: [thread](screenshots/messages-notifications/messages-thread-desktop-light.jpg), [colleague who has left, phone dark](screenshots/messages-notifications/messages-colleague-left-phone-dark.jpg). 🧪 🌐 👀

---

## Not built yet

The backend serves these, and the frontend has no screen for them — in the order of [Plan.md §9.3](Plan.md):

1. A direct order typed in line by line, and a consolidated order from several leads of one dealer (SO-005).
2. Editing and deleting a lead, the duplicates queue and merging.
3. Lead QR codes and the public enquiry form.
4. Tasks, the planner, meetings and minutes (on `integration` since #25).
5. Complaints, from entry to the quality check (on `integration` since #25).
6. Admin masters: products, price lists, tax rates, subsidy, users, offices, territories, partners.
