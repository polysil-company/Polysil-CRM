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
| [Quotations — the customer's link](#quotations--the-customers-link) | 2 | 🧪 👀 | `integration` |
| [Approvals](#approvals) | 5 | 🧪 👀 | `integration`; limits in PR #35 |
| [Sales orders and dispatch](#sales-orders-and-dispatch) | 9 | 🧪 👀 | PR #34; the Dispatch queue in PR #56 |
| [Tasks and the day planner](#tasks-and-the-day-planner) | 8 | 🧪 👀 | PR #54; minutes, edit and All tasks in PR #55 |
| [Complaints](#complaints) | 6 | 🧪 👀 | PR #57 |
| [Subsidy](#subsidy) | 9 | 🧪 👀 | calculator in PR #77; applications in PR #78 |
| [Dashboard, notifications, messages](#dashboard-notifications-messages) | 3 | 🧪 👀 | dashboard on the backend's contract in PR #41; bell and messages connected in PR #43 |

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
- **LEAD-001 · Filter by area** (backend #50, PR #53; screens: [districts](screenshots/area-filter/area-districts-desktop-light.jpg), [talukas in Rajkot](screenshots/area-filter/area-talukas-desktop-light.jpg), [filtered list](screenshots/area-filter/leads-filtered-by-rajkot-desktop-light.jpg), [phone, dark](screenshots/area-filter/area-districts-phone-dark.jpg)): the Area pill lists the districts that hold a lead you can see, each with how many — with one state, it starts at its districts. Tick several (up to 20; the rest are disabled with a note) or open a district to tick its talukas; a district takes in every taluka and village under it, and its count matches the filtered list. "All districts" goes back. The choice is in the URL (`?area=`), the pill names the area picked, and Clear or Reset filters removes it. States: loading, "no lead filed under a taluka — choose the district itself", an error with Try again. 🧪 👀
- **LEAD-002 · Create a lead.** Territory picker (districts on open, any district, taluka or village by typing; never the state, which a lead may not sit in: BE-005, PR #42, [screen](screenshots/backend-pickups/new-lead-no-state-desktop-light.jpg)), lookups from the administrators' lists, crops (up to 10, from `GET /lookups/crops`) and land in acres, a safe retry that never creates two leads, field errors on their fields. Dropdowns are not marked wrong just for being opened; they are checked on submit. A flagged duplicate is named in the toast, and several are counted ("3 possible duplicates (A, B and C)"), as on the lead page. 🧪 🔌 (crops, land and the duplicate count 🧪 👀 only)
- **LEAD-003 · Open a lead.** The real record: stage and priority (hot, warm or cold only while the lead is open), contact, territory, owner and office or "Unassigned", partner, score, crops (a switched-off crop greyed) and land, dates, the lost reason, a merged lead pointing to the lead it went into, possible duplicates with how they matched. No win probability or engagement cards (BE-004). The list shows crops and every value in whole rupees. 🧪 🌐 🔌 (crops and land 🧪 👀 only)
- **LEAD-004 · The lead count** in the sidebar and Sales tab is exact (`GET /leads/stats`), never capped. 🧪

## Leads — history, notes, stage, assign

Details and tests: [changelog entry](../changelog/entries/2026-09-27--feature--LEAD-005--lead-timeline-and-notes.md). Screens: [lost lead with its history](screenshots/leads/lead-lost-activity-desktop-light.webp) ([dark](screenshots/leads/lead-lost-activity-desktop-dark.webp), [phone](screenshots/leads/lead-activity-phone-light.webp)), [stage menu](screenshots/leads/lead-stage-menu.webp), [mark as lost](screenshots/leads/lead-mark-lost-dialog.webp), [assign](screenshots/leads/lead-assign-dialog.webp), [phone header, dark](screenshots/leads/lead-header-phone-dark.webp).

- **LEAD-005 · Read a lead's history** as sentences ("Ravi Joshi moved the lead from Qualified to Lost", with the reason and note), newest first, 20 at a time with "Show older activity". Covers notes, stage changes, reopenings, assignments, edits, merges, duplicate flags, quotation events with the quotation's number as a link ("QT/GJ/2026-27/00009 · v2"), approval steps ("approved the District Manager step"), and order and dispatch events with the dispatch number. An order's own number and link wait on BE-020. An unknown kind still reads well. States: skeleton, "No activity yet", error with retry, an older page failing without losing what is shown. 🧪 👀
- **LEAD-006 · Add a note** (anyone with `leads.edit`, not on a merged lead). Ctrl/⌘ + Enter saves, Enter adds a line; the note appears at the top at once; a counter near the 2,000-character limit; a failed save keeps the text, and a retry never adds it twice. 🧪 👀
- **LEAD-007 · Move the stage.** Update stage says what the current stage means, and what each move does (PR #45, [screen](screenshots/stage-help/stage-menu-phone-dark.jpg)). It offers only the moves allowed from the current stage: Contacted and Qualified in one click; Lost needs a reason (note optional); Won confirms; a lost lead can be reopened. Steps that happen on a quotation are listed but disabled with where they happen. If someone else moved the lead first, it says so and shows the latest; Won without an accepted quotation is explained. No menu on a won, merged or dormant lead, or without `leads.edit`. 🧪 👀
- **LEAD-008 · Assign the owner and channel partner** on an open lead (the history names them: "assigned the lead to Ravi Joshi and made Khodiyar Irrigation the channel partner", or "handed the lead from Asha Mehta to Ravi Joshi"; BE-006, PR #42, [screen](screenshots/backend-pickups/lead-history-assignment-desktop-light.jpg)): the people you may assign (or "Unassigned"), partners in your area by name, code or contact person (backend #49, PR #53). Only what changed is sent; an employee is told only a manager can change the owner; a refused partner shows on its field; no Assign on a closed lead. 🧪 👀
- **LEAD-010 · Edit a lead** (PR #68; screens: [the form](screenshots/leads/edit-lead-dialog-desktop-light.jpg), [saved](screenshots/leads/lead-edited-desktop-light.jpg)): **Edit** beside Assign on an open lead (`leads.edit`), with the same fields as New lead: name, mobile, email, territory, village, type, system, source, value, crops, land. Only the fields that changed are sent; a refused field is named on the form; a closed lead has no Edit (and the backend's `stage_terminal` is explained). The history says which fields changed. 🧪 👀
- **LEAD-011 · Delete a lead** (holders of `leads.delete` — Admin in the mock; [screen](screenshots/leads/delete-lead-dialog-desktop-light.jpg)): asks first, then goes back to the list; its pending duplicate pairs close. 🧪 👀
- **LEAD-012 · Possible duplicates** (`/leads/duplicates`, from the leads toolbar and from "Review and merge" on a lead's duplicate notice; screens: [queue](screenshots/leads/duplicates-desktop-light.jpg), [merge](screenshots/leads/merge-dialog-desktop-light.jpg), [a lead with a duplicate](screenshots/leads/lead-with-duplicate-desktop-light.jpg), [phone, dark](screenshots/leads/duplicates-phone-dark.jpg)): each pair side by side — name, stage, inquiry, mobile, place, owner, value, created — with what matched and how strongly. **Keep** one merges the other into it after a confirmation (its history moves across; it points to the kept lead); **Not a duplicate** clears the pair. A pair with a won or lost lead says it can't be merged and offers only Not a duplicate. States: skeleton, "No possible duplicates", Show more. 🧪 👀
- **LEAD-013 · QR codes** (PR #76; Sales → QR codes, for staff with `leads`; screens: [list](screenshots/lead-capture/qr-codes-desktop-light.jpg), [new code](screenshots/lead-capture/qr-new-dialog-desktop-light.jpg), [phone, dark](screenshots/lead-capture/qr-codes-phone-dark.jpg)): each code drawn as a QR (black on white in both themes, so it scans), with its name, on or switched off, its six-character code, how many leads it brought, campaign, dealer, area and age. **New QR code** (`leads.create`): name, campaign, dealer, area. **Download to print** saves a 1024-pixel PNG; **Copy link**; **Edit** and **Switch off/on** (`leads.edit`) — the code and its link never change, so printed copies keep working; a switched-off code's scans become plain website enquiries. A dealer the backend refuses is named on its field. 🧪 👀
- **LEAD-014 · The enquiry page** (`/enquiry`, no sign-in; screens: [with a dealer's code, phone](screenshots/lead-capture/enquiry-phone-light.jpg), [dark](screenshots/lead-capture/enquiry-phone-dark.jpg), [the WhatsApp code](screenshots/lead-capture/enquiry-code-phone-light.jpg), [the number](screenshots/lead-capture/enquiry-done-phone-light.jpg), [mistakes, desktop](screenshots/lead-capture/enquiry-errors-desktop-light.jpg)): "Enquiry through <dealer>" when a code opened it; name, mobile, the area (state → district → optional taluka, or "from the code you scanned" with "Choose another area"), village, the system, how they'll buy, a note. **Send me a code on WhatsApp**, then the six digits (with the time left, "Send a new code" after a minute, "Change my details"); a wrong code says so; too many codes says to wait. Then the inquiry number to keep — the same number when the mobile already enquired today. A code no longer in use opens the plain form and says so. In the mock any six digits match except `000000`. Checked at 360 px, light and dark. 🧪 👀

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

- **QUOT-012 · A customer opens their link** (`/q/…`) without signing in: the number, who it's from, the total including GST, the items count, when it was sent and until when it's valid, and **View quotation** opening the PDF in a new tab. The PDF opens only when tapped, so a WhatsApp preview is never counted as a view. While the PDF is made: "Preparing the PDF…", checked again by itself. Expired or replaced quotations still open, with a note. Nothing personal is shown, and the link's secret isn't passed on to the PDF's host. 🧪 👀
- **QUOT-012 · A wrong or cut-off link** says "This link doesn't open a quotation", with what to do. 🧪 👀

## Approvals

Details and tests: [changelog entry](../changelog/entries/2026-09-28--feature--APPR-001--approvals-inbox.md). Walked through as a State Manager: 7 requests; a rejection without a reason refused, then rejected with one; a quotation discount approved; lower steps added; on a phone in dark mode; an Employee sees no Approvals. Screens: [the inbox](screenshots/approvals/inbox-state-manager-desktop-light.jpg), [a reason to reject](screenshots/approvals/reject-needs-a-reason-desktop-light.jpg), [with steps below](screenshots/approvals/inbox-including-steps-below-desktop-light.jpg), [phone, dark](screenshots/approvals/inbox-phone-dark.jpg), [approve on a phone](screenshots/approvals/approve-dialog-phone-dark.jpg).

- **APPR-001 · See what waits on me** (whoever holds `sales_orders.approve` or `quotations.approve`: managers, Accounts, Dispatch): quotation discounts and sales orders side by side, oldest first — what it is, its number (or "Draft quotation"), the party, the total, the discount asked, stand-in pricing, who raised it and when, how long it has waited, and "Open the quotation" or "Open the order". An order's steps come one at a time: the next joins its inbox when the one before is approved. Accounts and Dispatch see only their own steps. A count in the sidebar (with a dot on the collapsed rail); the inbox and the count check every minute. States: skeleton, "Nothing waits on you", an error, a later page failing without losing what is shown. 🧪 👀
- **APPR-001 · Cover for a manager on leave:** "Include steps below me" (kept in the URL) adds lower managers' steps, each marked whose it is. A step nobody of its role covers always shows, marked "No District Manager to decide". 🧪 👀
- **APPR-001 · Approve or reject.** Rejecting needs a reason, which the person who asked reads; approving takes one optionally — except at Accounts, where every decision needs a remark (BE-018). The request leaves the inbox and the count drops; an approved quotation discount turns the officer's button into Send, a rejected one shows the reason on the draft. 🧪 👀
- **APPR-001 · Read why they asked** (backend #49, PR #53; screens: [the inbox](screenshots/approvals/inbox-with-reason-desktop-light.jpg), [the dialog](screenshots/approvals/decision-dialog-with-reason-desktop-light.jpg)): the remark the salesperson wrote when asking for discount approval shows under the row, and again at the top of the decision dialog ("Asha Mehta's reason: …"). Requests raised without one show nothing extra. 🧪 👀
- **APPR-002 · Approval limits** (Admin → Approval limits): the order-value ladder (District, State, Regional, including GST) the discount ladder (the field officer's own limit up to Admin-Sales), the refund ladder for complaints (District, State, Regional in rupees, then Accounts; PR #46), and a territory's own limits. A limit for a document the screen doesn't know yet is left out instead of failing the page (it failed on the dev API when refund limits arrived). An administrator (`masters.edit`) changes one level: the dialog gives the bounds in words, offers "No limit" only at the top, refuses a limit out of order on the field, and shows the new ladder at once; if another level changed meanwhile, it says so and reloads. Everyone else reads them. Screens: [admin](screenshots/approvals/limits-admin-desktop-light.jpg), [out of order](screenshots/approvals/limit-out-of-order-desktop-light.jpg), [changed](screenshots/approvals/limit-changed-desktop-light.jpg), [read-only on a phone, dark](screenshots/approvals/limits-read-only-phone-dark.jpg). 🧪 👀
- **APPR-001 · When the request moved on** — decided by someone else, withdrawn, or its draft edited after the request — the dialog closes, a toast says which, and the inbox shows the latest. Without the `approvals.approve` permission the rows show, the buttons don't. 🧪

## Sales orders and dispatch

Details and tests: [changelog entry](../changelog/entries/2026-09-30--feature--SO-001--sales-orders-and-dispatch.md). Walked through on the mock backend as a State Manager (list, a returned order edited and submitted again, an order step approved in the inbox), as Dispatch (record with mistakes then correctly, void, close short), and as a field officer on a phone (place an order from an accepted quotation). Screens: [list](screenshots/orders/list-desktop-light.jpg) ([dark](screenshots/orders/list-desktop-dark.jpg), [phone](screenshots/orders/list-phone-light.jpg)), [returned order](screenshots/orders/returned-draft-desktop-light.jpg), [submit](screenshots/orders/submit-dialog-desktop-light.jpg), [waiting on its chain](screenshots/orders/submitted-approval-chain-desktop-light.jpg), [partly dispatched](screenshots/orders/partly-dispatched-desktop-dark.jpg), [record: mistakes](screenshots/orders/record-dispatch-errors-desktop-dark.jpg), [record: filled](screenshots/orders/record-dispatch-filled-desktop-dark.jpg), [dispatched](screenshots/orders/fully-dispatched-desktop-dark.jpg), [voided](screenshots/orders/voided-dispatch-desktop-dark.jpg), [closed short](screenshots/orders/closed-short-desktop-dark.jpg), [place order](screenshots/orders/place-order-dialog-phone-light.jpg), [new draft on a phone](screenshots/orders/new-draft-order-phone-light.jpg), [detail on a phone, dark](screenshots/orders/detail-phone-dark.jpg).

- **SO-001 · Browse orders,** newest first: number (or "Draft order"), dealer or "Direct sale", "Provisional", the party, the status with whom it waits on ("Waiting on Accounts"), how much has shipped (a share and a bar), type, owner, created, total. Filter by several statuses, one type, "Only my orders", and search by number, party or mobile — all kept in the URL. States: skeleton, "No sales orders yet", nothing matches, a page link that no longer works, an emptied page, errors. 🧪 👀
- **SO-002 · Open an order:** the lines with ordered, sent, open and short once approved; totals with CGST and SGST or IGST; the approval chain step by step (who decided, when, their remark, "Waiting now", covered by a higher manager); dispatches; party, quotations it came from, delivery, payment terms, place of supply, seller; its history; "Open PDF" once approved ("Preparing PDF…" while it renders, checked again by itself). Notices: returned with the reason, cancelled or closed short with the reason, indicative pricing, no mobile for the confirmation, the PDF failed. 🧪 👀
- **SO-003 · Place an order** from an accepted, current quotation ("Place order" for roles with `sales_orders.create`): order type (commercial or industrial), delivery address (the party's by default), payment terms, remarks; the draft opens. A quotation already on a live order shows "Open order" instead, found with one `GET /orders?quotation_id=` call (BE-019, PR #42). 🧪 👀
- **SO-003 · Change a draft's delivery, terms and remarks;** delete a draft that was never submitted (holders of `sales_orders.delete` — Admin in the mock); a numbered draft is cancelled instead. 🧪 👀
- **SO-005 · A direct order, typed in** (PR #59; screens: [empty](screenshots/orders/new-order-empty-desktop-light.jpg), [priced](screenshots/orders/new-order-priced-desktop-light.jpg), [the draft](screenshots/orders/direct-order-draft-desktop-light.jpg), [editing it](screenshots/orders/edit-order-desktop-light.jpg), [afresh](screenshots/orders/new-order-afresh-desktop-light.jpg), [phone, dark](screenshots/orders/new-order-phone-dark.jpg)): **New order** on a qualified lead (or one further on) and on the orders list, for roles with `sales_orders.create`. Items are picked and priced by the backend as they are typed, as in the quotation builder; the party, mobile, GSTIN and address come from the lead, the place of supply is the lead's (or chosen, for an order typed in afresh, before anything is priced), with order type, delivery address, payment and remarks. Save is off until there is a place and an item; it says why. A price that moved since the preview is named on its line and priced again. A new lead says it can't take an order yet; a role without create sees no access. **Edit items** on a draft changes its items and header; an order made from quotations keeps the party they fixed; a submitted one can't be edited. 🧪 👀
- **SO-006, LEAD-009, QUOT-013 · Download Excel** on the order, lead and quotation lists (PR #59, [screen](screenshots/orders/orders-list-actions-desktop-light.jpg)): the rows the filters show, every page, saved under the backend's name (`orders-2026-10-04.xlsx`). More than 5,000: "narrow the filters". 🧪 👀
- **SO-004 · Submit for approval,** or "Submit again" after a return: the order gets its number and waits on its managers by value, then Accounts, then Dispatch. Cancel with a reason — the owner while it is a draft or waiting, a holder of delete once approved, nobody once something has shipped. 🧪 👀
- **DISP-002 · Record a dispatch** (Dispatch, `dispatch.create`): each open item's quantity (or "Everything open"), when it left, challan, invoice, transporter, vehicle. Refused on the field: nothing entered, more than is open, decimals on a whole-unit item, a time in the future. An invoice dated before its challan, or an invoice number already used, is recorded with a warning. The order moves to Partly dispatched or Dispatched. 🧪 👀
- **DISP-002 · Void a dispatch** with a reason — it stays on record, struck through, and its quantities are open again — and **close the rest short** with a reason. Managers see neither. When someone else moved the order first, the dialog closes, a toast says what happened, and the page shows the latest. 🧪 👀
- **DISP-001 · The Dispatch queue** (Dispatch, or anyone with `dispatch`; PR #56; screens: [to ship](screenshots/dispatch/to-ship-desktop-light.jpg), [to ship, phone dark](screenshots/dispatch/to-ship-phone-dark.jpg), [record from the queue](screenshots/dispatch/record-from-queue-desktop-light.jpg)): **To ship** lists every approved order still waiting to leave, partly sent ones with how much has gone ("46% sent"), with the count. **Record a dispatch** opens the order with the form already open (`?record=dispatch`); someone who may only look sees no button, and the link does nothing for them. States: skeleton, "Nothing waiting to ship", an error, a later page failing. 🧪 👀
- **DISP-001 · The dispatch log** (PR #56; screens: [desktop](screenshots/dispatch/dispatched-desktop-light.jpg), [phone, dark](screenshots/dispatch/dispatched-phone-dark.jpg)): **Dispatched** lists what left, newest first — dispatch number, the order (linked) and party, items, challan, invoice, transporter and vehicle, who recorded it — voided ones marked with their reason. Between two days (in the URL), or any day; "Nothing sent on these days" otherwise. The **Accounts queue** waits on the backend (BE-022); Accounts' steps are in their Approvals inbox meanwhile. 🧪 👀

## Tasks and the day planner

On the backend's contract (`backend/docs/api/tasks.md`) since PR #54 ([changelog](../changelog/entries/2026-10-04--feature--TASK-001--tasks-my-day-team-day-and-a-lead-s-tasks.md)). Walked through in the mock, as an admin with a team and as an officer, on a desktop in light mode and on a phone in dark mode; axe found nothing on My day, Team, a person's day, Mark done or New task. Not yet checked on the dev API. Screens: [My day](screenshots/tasks/my-day-desktop-light.jpg), [phone, dark](screenshots/tasks/my-day-phone-dark.jpg), [Team](screenshots/tasks/team-day-desktop-light.jpg), [a person's day](screenshots/tasks/person-day-desktop-light.jpg), [Mark done](screenshots/tasks/mark-done-desktop-light.jpg), [New task](screenshots/tasks/new-task-desktop-light.jpg), [New task, phone](screenshots/tasks/new-task-phone-dark.jpg), [on a lead](screenshots/tasks/lead-tasks-desktop-light.jpg).

- **TASK-001 · My day** (staff with `tasks`; dealers have none): what is overdue from earlier on top (up to 90 days back), then what is due that day by time. Each task shows its kind, time, meeting type, the lead (linked) or dealer it is about, who gave it, and its notes. Done tasks show what happened; cancelled ones show why. The server says what is overdue; the screen never works it out. Previous day, next day, any date, and back to today. A future day has nothing overdue. The day is in the URL (`?date=`). States: skeleton, "A clear day", an error with retry. 🧪 👀
- **TASK-002 · Team** (managers and admins: anyone with a team): one row per person below them, with due that day, done that day and overdue now. People with nothing to do are listed too. A row opens that person's day (`?user=`, sent as a link), with "Back to team"; a new task from there is for them. Officers see no Team. 🧪 👀
- **TASK-003 · A lead's tasks and meetings** on its page: what is still to do, by due date, then what was done or cancelled, each saying who it is for. A merged lead takes no new tasks. 🧪 👀
- **TASK-004 · New task:**
  - what to do, the kind (call, visit, meeting, follow-up, other), the day, an optional time (otherwise due at 18:00), who it is for (yourself, or someone below you), and notes;
  - from a lead it is about that lead, and a meeting names its kind (Survey & Design, Follow-up…);
  - field errors from the server land on their fields; a retry reuses its key, so no second task is made. 🧪 👀
- **TASK-005 · Done, cancel, reopen:**
  - Done asks what happened, and for a meeting whether the gift was shown;
  - cancelling asks why. A task someone else gave you can't be cancelled by you, only by them, so the option isn't offered;
  - a done task can be reopened by whoever it is for or whoever gave it. After 7 days the backend says to add a new task;
  - a task someone moved on meanwhile closes the dialog and refreshes. 🧪 👀

- **TASK-006 · Edit or reassign** an open task from its menu (PR #55, [screen](screenshots/tasks/edit-task-desktop-light.jpg)): what to do, the day and time, notes, and who does it (a manager's team; an officer's field says only a manager can give it to someone else). Only what changed is sent, with `expected_status: open`, so a task done meanwhile is refused and the list refreshes. "Given to Ravi Joshi" confirms a reassignment. 🧪 👀
- **TASK-007 · Meeting minutes** on a lead's page (PR #55; screens: [the minutes](screenshots/tasks/lead-minutes-desktop-light.jpg), [recording them](screenshots/tasks/record-minutes-desktop-light.jpg)): newest first, with when, who was there, what was discussed, and each action item as its task stands now ("1 of 2 done", overdue in red). **Record minutes** from the card, or from a planned meeting's menu, which then marks that meeting done. Who was there is one per line; each action item (what, due day, for whom, kind) becomes a task, marked "From meeting minutes". One save: an item the backend refuses (say, someone the user can't assign) keeps everything unsaved and points at that item. 🧪 👀
- **TASK-008 · All tasks** (PR #55; screens: [desktop](screenshots/tasks/all-tasks-desktop-light.jpg), [phone, dark](screenshots/tasks/all-tasks-phone-dark.jpg)): everything the user can see, earliest due first, with a count; filters for status, kind, person (managers) and overdue only, all in the URL; **Download Excel** saves the same tasks as a file named by the backend (`tasks-2026-10-04.xlsx`), every page. More than 5,000 rows: "Too many tasks to download — narrow the filters". States: skeleton, "No tasks match these filters" with Reset, a later page failing. 🧪 👀

---

## Complaints

On the backend's contract (`backend/docs/api/complaints.md`, handover `complaints-contract.md`) since PR #57 ([changelog](../changelog/entries/2026-10-04--feature--CMPL-001--complaints-raise-check-and-qc.md)). Walked through in the mock: raised as Admin with mistakes then correctly, submitted, checked, given a QC verdict; a District Manager's queue on a phone in dark mode. axe found nothing on the list, the form, the complaint, or the check and QC dialogs. Not yet checked on the dev API. Screens: [list](screenshots/complaints/list-desktop-light.jpg), [form mistakes](screenshots/complaints/new-errors-desktop-light.jpg), [a draft](screenshots/complaints/draft-desktop-light.jpg), [submitted](screenshots/complaints/submitted-desktop-light.jpg), [check](screenshots/complaints/check-dialog-desktop-light.jpg), [QC](screenshots/complaints/qc-dialog-desktop-light.jpg), [QC approved](screenshots/complaints/qc-approved-desktop-light.jpg), [waiting on me, phone dark](screenshots/complaints/waiting-on-me-phone-dark.jpg), [a complaint on a phone](screenshots/complaints/detail-phone-dark.jpg).

- **CMPL-001 · The complaints list** (anyone with `complaints`): newest first, with the number (or "Draft complaint"), status, severity, a red "Late" when a target was missed, the contact, type, dealer and owner (or "No owner yet"), and how long ago. Counts above: waiting for a check, with QC, late. Search by number, contact or mobile; filter by status (each explained), severity, type, late only, no owner — all in the URL. States: skeleton, "No complaints yet", nothing matching with Reset, an error, a later page failing. 🧪 👀
- **CMPL-001 · Waiting on me** (managers and QC): what waits for their check or verdict, oldest first. Someone who can only look (Accounts) sees neither the queue nor "New complaint". 🧪 👀
- **CMPL-003 · Raise a complaint and edit the draft:** type, severity, what went wrong, the contact and mobile, where it is installed, the dealer, the challan and supply date (needed to submit; not after today), registration and PIMS numbers, the sample's courier; products with supplied and defective (1 to 20, each once, defective not more than supplied). Every mistake is named on its field at once. Editing sends only what changed. From a lead's or an order's page (`?lead=`, `?order=`) it is about them. 🧪 👀
- **CMPL-003 · Submit, cancel, delete:** submitting numbers it (`Poly/Comp./2026-27/GJ/NN`) and starts the targets; without the challan or supply date it says which to add; with nothing defective it says so. A returned draft says who returned it and what to fix, and offers "Submit again". Cancel needs a reason, shown on the complaint; a draft never submitted can be deleted. 🧪 👀
- **CMPL-004 · The manager's check:** approve it to QC (optionally a new severity and an owner) or return it to fix, with a remark the raiser reads — a dealer included — and an internal note staff alone see. Someone who checked it first: the dialog closes and the page shows the latest. 🧪 👀
- **CMPL-005 · The QC verdict:** approved (a defect; a remedy follows) or rejected (no defect; it closes), what QC found, and the sample's received, tested and field-visit dates (not after today; not before supply). The complaint shows the check and the verdict, the targets met or missed with their due times, and its history. 🧪 👀

The rest of complaints (PR #58, stacked on #57; [changelog](../changelog/entries/2026-10-04--feature--CMPL-006--complaint-files-remedies-and-targets.md)). Walked through in the mock: QC added a photo to a complaint under QC, chose a ₹1,500 refund on a QC-approved one (first with every field empty), the District Manager approved it in the Approvals inbox, Accounts approved it with the payment reference, and the complaint closed showing the reference; the targets as Admin on a desktop and on a phone in dark mode. axe found nothing on the complaint, the remedy dialog, the inbox, the payment dialog, the targets and their dialog. Not yet checked on the dev API. Screens: [files](screenshots/complaints/files-desktop-light.jpg), [remedy, empty](screenshots/complaints/remedy-dialog-errors-desktop-light.jpg), [remedy](screenshots/complaints/remedy-dialog-desktop-light.jpg), [refund waiting](screenshots/complaints/refund-pending-desktop-light.jpg), [in the inbox](screenshots/complaints/inbox-refund-desktop-light.jpg), [Accounts pays](screenshots/complaints/accounts-pay-dialog-desktop-light.jpg), [paid and closed](screenshots/complaints/refund-paid-desktop-light.jpg), [a QC-approved complaint, phone dark](screenshots/complaints/qc-approved-phone-dark.jpg), [targets](screenshots/complaints/targets-desktop-light.jpg), [new target](screenshots/complaints/target-dialog-desktop-light.jpg), [targets, phone dark](screenshots/complaints/targets-phone-dark.jpg).

- **CMPL-006 · Files** on a complaint: photos as thumbnails from a ten-minute link (re-read before it expires), HEIC and PDF as files to open, each with its kind (photo, document, challan), size and when. Whoever may add files picks a kind and one or more files; each is checked first (JPEG, PNG, WebP, HEIC or PDF; 10 MB; 10 per complaint) and sent on its own, with "Uploading…", and a failure keeps its reason with **Try again**. While the complaint is a draft or submitted, whoever may raise complaints adds files; under QC, only QC; after that, nobody. Removing a file asks first; after submit only whoever added it may. When file storage isn't set up the card says so and offers no upload. 🧪 👀
- **CMPL-007 · The remedy** (QC, once QC found a defect): a **refund** (amount, who is paid, optionally through a dealer, why), a **replacement** order, or **no action**, which closes it at once; each says what happens next. A refund goes to the managers by amount, then Accounts, and the card shows each step, who decided and the payment reference once paid; QC may **withdraw** it while open. A refund turned down goes back to QC to choose again, and says so. The history names each step: sent for approval, paid, not approved, withdrawn. 🧪 👀
- **APPR-001 · Refunds in the Approvals inbox:** a "Complaint refund" row with the amount, the payee and **Open the complaint**. A manager approves or rejects it like an order; Accounts must enter the payment reference (the UTR or cheque number) to approve, which closes the complaint. 🧪 👀
- **CMPL-008 · Complaint targets** (Admin → Complaint targets; anyone with complaints reads them): each severity's first-response and resolution target, in working hours (Monday to Saturday, 09:30 to 18:30) or round the clock, with its start day and whether it is in force, scheduled or ended (past ones on request). Those who may edit masters set a new target from a day (not in the past; resolution not quicker than the response; for every type or one type); the one in force ends that day, and complaints already submitted keep theirs. 🧪 👀
- **CMPL-009 · Download Excel** on the complaints list: the complaints matching the filters on screen, as a file named by the backend. More than 5,000: "narrow the filters". 🧪
- **CMPL-001 · A lead's and an order's complaints:** a Complaints card on the lead's page and on a submitted order's, newest first, with **Raise a complaint** about it (not on a merged lead). Hidden from those who can't see complaints. 🧪

Complaint types are set with the other lookups, in the admin masters.

---

## Subsidy

On the backend's contract (`backend/docs/api/subsidy.md`, handover `subsidy-calculation.md`) since PR #77 ([changelog](../changelog/entries/2026-10-09--feature--SUBS-002--the-subsidy-calculator.md)). Walked through in the mock as a field employee: Drip with a crop, three field-unit items, two head-unit items and installation, then a group area the backend refused and a spacing with three decimals; Drip with two crop blocks in dark mode; Sprinkler on a 360 px phone in dark mode, with no sideways scroll. axe found nothing on any of them. The mock's figures are a stand-in for the engine's; not yet checked on the dev API. Screens: [empty, phone](screenshots/subsidy/calculator-empty-phone-light.jpg), [Drip](screenshots/subsidy/calculator-drip-desktop-light.jpg), [mistakes](screenshots/subsidy/calculator-mistakes-desktop-light.jpg), [two crop blocks, dark](screenshots/subsidy/calculator-two-blocks-desktop-dark.jpg), [Sprinkler, phone dark](screenshots/subsidy/calculator-sprinkler-phone-dark.jpg).

- **SUBS-003 · Three systems from the scheme's config** (Sales → Subsidy, staff with `subsidy`; dealers and distributors neither see it nor reach it — the backend answers them 403): Drip, Mini Sprinkler and Sprinkler as three tabs (`?system=`), each shaped by `GET /subsidy/config` — how many crop blocks (two on Drip), a head unit and a group's area or not, Sprinkler's areas. Each tab keeps its own inputs. Before anything is calculated, the eight farmer categories are listed with their percentages. The crop pickers show each crop's standard spacing. 🧪 👀
- **SUBS-002 · The calculation as the designer types:** crop and inter-crop, area, lateral spacing, crop spacing and field-unit items per block; the head unit once; installation and sump per hectare; a group's total area; Sprinkler's nozzle. After a pause the figures follow: the warnings (titled, naming the block, the seven-year ones apart); each block's designed, standard and used spacing — with why when the standard wins — the unit cost the scheme allows (`regular_for_cap`) and the seven-year one; all eight categories with the subsidy, its share and what the farmer pays (with GSDMA on small Mini Sprinkler areas), a category that doesn't apply greyed with its reason; and the 22-row summary, a column per block and the total. The figures are printed as the backend sends them, never added up on screen. Nothing is saved. 🧪 👀
- **SUBS-002 · Sprinkler:** the area from the scheme's steps only, no lines and no head unit; the result lists the derived items, the pipe size and the DBT farmer payable. 🧪 👀
- **SUBS-002 · Mistakes and refusals:** a missing area or spacing just waits; too many decimals, a half-typed item or a group area of 0 are named on the field once typing pauses; a refusal from the backend (`crops[0].area`, `group_total_area`…) lands on the same field, and one no field shows (too many blocks) is listed above the figures. Older figures stay dimmed while new ones load. A failure no field explains shows an error with a retry. 🧪 👀


Subsidy applications (PR #78, stacked on #77; [changelog](../changelog/entries/2026-10-09--feature--SUBS-004--subsidy-applications.md)). Walked through in the mock as a field employee:
1. A quoted drip lead's card, then "Start subsidy application".
2. The design, a category and a survey number, then started.
3. A Reg. No. recorded at stage 4: first refused for want of a remark, then given one.
4. The stored calculation, and the PIMS sheet downloaded.
5. The worklist and an application on a 360 px phone in dark mode, with no sideways scroll.

axe found nothing on any of them. Not yet checked on the dev API. Screens: [worklist](screenshots/subsidy/applications-desktop-light.jpg), [the lead's card](screenshots/subsidy/lead-card-desktop-light.jpg), [start](screenshots/subsidy/start-desktop-light.jpg), [just started](screenshots/subsidy/application-new-desktop-light.jpg), [record stage, a mistake](screenshots/subsidy/record-stage-mistake-desktop-light.jpg), [an application](screenshots/subsidy/application-desktop-light.jpg), [worklist, phone dark](screenshots/subsidy/applications-phone-dark.jpg), [an application, phone dark](screenshots/subsidy/application-phone-dark.jpg).

- **SUBS-004 · Start an application from a lead.** A subsidised lead's page has a "Subsidy application" card (staff with `subsidy`).
  - "Start subsidy application" shows when all of these hold:
    - the lead is qualified, quoted, in negotiation or won;
    - its system is drip, mini sprinkler or sprinkler;
    - there is no live application;
    - the user may change applications.
  - Otherwise the card says why.
  - The start page is the calculator for the lead's system. Then the farmer's category: only those that apply on every crop block, each with its subsidy. Then an optional survey number.
  - Start stays off until the figures are in. Without a category it asks for one.
  - Starting moves the lead to won and opens the application at stage 4.
  - The calculation runs under the lead's state's scheme (`GET /subsidy-schemes/for-lead`). A state with no scheme, or one not ready, says "Subsidy for this state is not set up yet".
  - Refusals say what is wrong: not subsidised, not forwardable, no calculation for the system, already forwarded, a category that doesn't apply, a calculation field.
  - 🧪 👀
- **SUBS-005 · The worklist** (Subsidy → Applications), newest first.
  - Each row: number, status, Reg. No., subsidy, farmer, stage, days in the stage, area and inquiry.
  - Filters: status, stage (from the scheme's list) and a search on number, Reg. No. or farmer. All of them live in the URL.
  - Download Excel.
  - States: skeleton, "No applications yet", nothing matching with Reset, Show more.
  - 🧪 👀
- **SUBS-006 · The application.**
  - Shows:
    - the number, status, farmer, the lead's inquiry, system and scheme;
    - the current stage, since when and for how many days; the Reg. No.; days since inward; documents on the checklist;
    - the figures: subsidy, what the farmer pays, total cost and area;
    - the farmer, the dealer and the owner;
    - every stage entry, oldest first: its values, who entered it, the remark, and "Back" when it went back;
    - on request, the calculation as stored, never recalculated.
  - **Record stage** builds its form from `GET /subsidy-stages`:
    - a date (not after today), and each field as a date, rupees or text, starting from what it holds now;
    - only the fields that changed are sent, so nothing is cleared by accident;
    - a remark is needed going back or repeating a stage;
    - two decimals at most for amounts.
  - A closed application says it is fully paid. A cancelled one shows its reason and takes no entries; a 409 says so.
  - **Cancel** asks for a reason. Afterwards the lead can start again.
  - View-only roles (Regional Manager, Accounts) see the application but get no buttons.
  - 🧪 👀
- **SUBS-007 · Documents:** the 20-item checklist. Each item shows its files, opened through a ten-minute link.
  - Whoever may change the application adds files to an item.
  - Each file is checked first: PDF, JPEG, PNG, WebP or HEIC, 10 MB, 40 per application. Then each is sent on its own, with "Uploading…" and **Try again**.
  - "Files can't be stored right now" covers a `503`.
  - 🧪 👀
- **SUBS-008 · PIMS sheet:** a download from the application, GGRC applications only (GAP-363). 🧪 👀

---

## Dashboard, notifications, messages

The dashboard reads the backend's real shape since the demo-walk fixes ([changelog](../changelog/entries/2026-10-02--fix--RPT-001--demo-walk-fixes.md)). The bell and messages follow the backend's contracts (BE-009, BE-010) since PR #43 ([changelog](../changelog/entries/2026-10-02--api-integration--NOTIF-001--notifications-and-messages-on-the-backend.md)). None of the three has been checked on the dev API by hand yet. Details and tests: [dashboard (foundation)](../changelog/entries/2026-09-14--feature--APP-001--frontend-foundation.md), [notifications and messages](../changelog/entries/2026-09-15--feature--NOTIF-001--notification-bell-and-staff-messages.md).

- **RPT-001 · The dashboard,** read in the backend's own shape (BE-008): open pipeline value, new leads, conversion and overdue follow-ups, each with its change and trend where the backend gives one; the pipeline by stage with value; leads by source; the next follow-ups, marked overdue. Money stays a decimal string until it is printed. Screens: [desktop](screenshots/demo-fixes/dashboard-desktop-light.jpg), [phone, dark](screenshots/demo-fixes/dashboard-phone-dark.jpg). 🧪 👀
- **NOTIF-001, NOTIF-002 · The notification bell** in the top bar (any signed-in user).
  - The badge counts the unread, checking every 30 seconds with one notification's worth of data.
  - Opening it lists the latest 20, each with its own icon for the backend's 14 kinds; an unknown kind gets the plain bell.
  - A notification opens its lead, quotation, sales order or complaint (PR #57). Tasks have no page of their own yet, so theirs only mark read.
  - Mark one or all read: the badge drops at once, is put back if the call fails, then takes the backend's count.
  - States: skeleton, "You're all caught up", an error with retry.
  - Screens: [desktop](screenshots/messages-notifications/notifications-bell-desktop-light.jpg), [phone, dark](screenshots/messages-notifications/notifications-bell-phone-dark.jpg). 🧪 👀
- **MSG-001 … MSG-005 · Direct messages between staff** (staff only; partners are told messages are for staff), and sharing a lead with a colleague from its page.
  - Conversations, most recent first, with unread counts.
  - The thread, grouped by day. Opening it marks read up to the newest message on screen, so one that arrives meanwhile stays unread.
  - Enter sends, Shift + Enter adds a line; a failed send puts the text back.
  - A lead the sender can't see is refused with a reason.
  - A new conversation keeps its colleague's name until the first message lists it.
  - A colleague who has left: the conversation stays readable and closed. If the backend refuses a send because they have left, the draft stays to copy.
  - Screens: [thread](screenshots/messages-notifications/messages-thread-desktop-light.jpg), [colleague who has left, phone dark](screenshots/messages-notifications/messages-colleague-left-phone-dark.jpg). 🧪 👀

---

## Not built yet

The backend serves these, and the frontend has no screen for them — in the order of [Plan.md §9.3](Plan.md):

1. A consolidated order from several quotations on leads of one dealer.
2. Complaint types, with the other lookups in the admin masters. Everything else in complaints is in PR #57 and PR #58.
3. The subsidy reports (ageing, stages, supply) and the masters' revisions.
4. Admin masters: products, price lists, tax rates, users, offices, territories, partners.
