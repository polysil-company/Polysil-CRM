# Staging walk of 10 Oct: what changed, and what is yours

The walk report has 20 findings. This note covers the first set of backend fixes, the API changes that come with them, and the findings that belong to the frontend. The other backend fixes (channel partner on quotations and orders, partner search, the thresholds 403, QR lead owners, dashboard counts, the PDF, the score) come in its own note.

## API changes

All additive. Nothing you built breaks.

| Where | Change | Use it for |
|---|---|---|
| `GET /leads/{id}/timeline` | For a dealer: no staff notes, no duplicate flags, dismissals or merges, and no lost reason or notes on stage changes and reopens. The dealer's own notes stay. | Nothing to do. The Activity tab shows less to a dealer. |
| `GET /leads/{id}`, `GET /leads`, the export | For a dealer: `score`, `lost_reason` and `lost_note` are null and `duplicates` is empty. | Hide the score and the "possible duplicates" box when `score` is null and the list is empty. |
| `GET /leads/duplicates` | Empty for a dealer. `POST /leads/duplicates/{id}/dismiss` is 403 for a dealer, as merge already was. | Hide the "Possible duplicates" button for a partner user. |
| `lead.merged` payload | New `loser_inquiry_no`, `survivor_inquiry_no`. Each merge is one entry now, not two. | "Asha Patel merged POL/GJ/2026-27/00094 into this lead." |
| `lead.duplicate_flagged` payload | Each of `matches` has `inquiry_no`. A new entry is written only when new pairs are found; an edit that finds the same pairs writes nothing. | "6 possible duplicates found: 00083, 00088, ..." The system found them, so say "found", not "<person> flagged". |
| `lead.duplicate_dismissed` payload | New `other_lead_id`, `other_inquiry_no`. | "Asha Patel marked 00083 as not a duplicate." |
| `approval.steps[].stalled` (orders, quotations and a complaint's refund) | True on the step waiting now when nobody of that role can decide it. A higher manager decides it and has it in their inbox. | Show "No District Manager to decide. With the next manager up." instead of "Waiting on District Manager" (F-11). |

A number in these payloads is null when the reader cannot see that lead. A dealer's timeline page can come back with fewer entries than `limit`, even none, and still a `next_cursor`: keep paging while there is one.

## WhatsApp

- F-2: each quotation and order message went out 2 or 3 times. 11za answered after 10 seconds, and the worker resent. Fixed: it waits 30 seconds, and a message with no answer is not resent, except a sign-in code.
- F-3: complaint messages do not go out yet. The two complaint templates are not created in 11za. Until they are, the complaint form should not promise "They get a WhatsApp at each step". Say "They get a WhatsApp at each step, once messages are switched on", or drop the line.
- F-3: the second lead on the same mobile within a day gets no thank-you message. That is on purpose: one a day per number.

## Still open, not yours

- F-5: the resolution target ends at the QC verdict, not when the remedy is done. This is a recorded choice waiting on the client (question 7.1).
- F-10: staging has no Regional Manager login.

## Yours (frontend)

| # | What |
|---|---|
| F-1 | The dealer sees the score, the duplicates box and the "Possible duplicates" button. Hide them for a partner user (the API now sends null and empty lists). |
| F-8 | The dealer opens `/approval-limits`, `/qr-codes` and `/dispatch` by URL. Add the route guards. The approval limits page asks the user to "Ask the backend team to seed them". Say "No approval limits are set." |
| F-9 | The channel partner box holds "No channel partner" as editable text, so typing appends to it and searches `No channel partnerBhavesh`. Use a placeholder. |
| F-11 | Use `stalled` on the step (above). |
| F-12 | Files on a complaint cannot be added after the QC verdict. Confirm this is meant. |
| F-13 | The first click after a page loads is ignored on `/tasks`, `/leads`, the lead page and `/approvals`. On `/approvals`, the next Approve after a decision needed up to 4 clicks. |
| F-14 | "Preparing PDF" did not clear without a reload after Send. If the poll runs only in a focused tab, a user who goes to WhatsApp and back never sees "Open PDF". |
| F-16 | Timeline text: use the new numbers. "Quotation discount approved Draft": a draft has no number, so say "draft quotation v1". "the customer · Quotation opened by the customer QT/..." repeats itself; say "The customer opened QT/...". One discount decision gives two lines (the step and the discount); show one. |
| F-17 | Access-denied pages show "REF TASK-001 · <uuid>". Drop the reference, and do not draw the page behind the message. |
| F-19 | Dealer sign-in says the code comes "by SMS"; it comes on WhatsApp. The enquiry form shows the QR code's internal label to the farmer, reads "Loading…" before a state is picked, and submits on the sixth digit. An em dash on the QR codes page. "Your territory at a glance" for admin and MD. Order dialog copy for orders typed in directly. "10.00 defective of 100.00 NOS." No confirm before a complaint submit, which messages the contact. The Reason box turns red as soon as it opens. |
| F-19 | Menus: a field officer has Assign on a lead and QR codes, Dispatch queue and Complaint targets in the menu. Confirm with the role table which of these he should have. |
| F-20 | The theme button: check by eye that Light gives a light page. |
