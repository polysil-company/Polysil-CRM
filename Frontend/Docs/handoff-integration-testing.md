# Handoff: test the hosted integration app and write a report

**Prompt for the agent:** read this file, then `Frontend/Docs/Live-Test-Plan.md` (especially §0 and "For an agent running this plan"), then `Frontend/AGENTS.md`. Test the hosted **integration** app as described here, and deliver the report in one PR against `integration`.

Ask the user only when blocked: a missing URL, a missing login, or the network refusing the host. For anything else, make a reasonable choice and note it in the report.

## What you get from the user, in the chat or as environment secrets

| Input | Notes |
| --- | --- |
| `APP_URL` | The hosted **integration** frontend. |
| The staff password | One password for every staff account. The accounts are listed in `backend/docs/handover/dev-api-access.md`: `admin@`, `gujarat@`, `asha@`, `ravi@`, `accounts@`, `dispatch@`, `quality@` and the others `@polysil.in`. |
| A test mobile number (optional) | The only number you may create records with or send WhatsApp to. Without it, never press "Send on WhatsApp". |
| A dealer one-time code (optional) | The backend reads it from the database for `919876543210`. Without it, mark the partner-portal cases ⛔. |

## The rules (on top of Live-Test-Plan §0.2)

1. **Only integration, never staging.**
   - Staging (`polysil-test.pranayx.tech`) is the client's live box with their own data.
   - If `APP_URL` is that host, or you aren't sure which environment it is, **stop and ask**.
2. **Credentials never go in any file, screenshot, report, commit or log line.**
   - Read them from environment variables or the chat.
   - Mask password fields before any screenshot.
3. **Everything you create is named `TEST …`, and is listed in the report's clean-up section.**
4. **Leave other people's data alone:**
   - never delete, cancel or edit a record you didn't create;
   - never message a real customer.
5. **Approval limits:** if you change one (case M-03 only), put back the exact old value straight after.
6. **Never restart anything** on the box. It hosts other services.
7. **Screenshots in the repo:** only ones showing `TEST` records or no personal data, and no password fields. Otherwise describe what you saw in words.
8. **Don't fix code during the run.**
   - Record failures (Live-Test-Plan §0.6) and move on.
   - A backend bug or missing field becomes a new `BE-NNN` in `docs/Backend-Tasks.md`, in that file's format (the next free number after BE-033).
9. **Out of scope:**
   - the Android app (TRK-008). Its Duty screen shows only inside the app;
   - don't touch `RELEASED_NAV`.

## Save as you go (your usage may run out)

- Start a branch from `integration`: `test/live-integration-<yyyy-mm-dd>`.
- After **each section**, update `Frontend/Docs/Live-Test-Report.md`, commit and push. A run that stops halfway still leaves a useful report.
- Open the PR (base `integration`) after the first section, and keep pushing to it.

## What to test, in this order

**Priority 1: what the client uses, plus today's merges.**

- **a. The 13 screens released on staging:**
  - Dashboard, Messages, Leads, QR codes, Quotations, Sales orders;
  - Approvals, Tasks, Dispatch, Approval limits;
  - Products, Users, Channel partners.
  - Use Live-Test-Plan §A–§Q and §S for those that have cases. For **Tasks, QR codes, Products, Users and Channel partners**, write the cases yourself (see "New cases" below).
- **b. What merged on 22 Oct:**
  - **MSTR-005, HSN on the New product form:**
    - add a `TEST` product with an HSN; it should no longer show "No HSN";
    - add one with a bad code: the field says why.
  - **BE-023 to BE-030** (#193):
    - a lead's subsidy card;
    - the product form's category and unit pickers;
    - scheme target names;
    - document types offered on a lead;
    - order, quality and kind in Masters;
    - Place order only offering quotations that are free to order;
    - a dealer's pages making no refused `GET /tasks`.
  - **QUOT-015, a GST slab per item and freight** (#192). On a **commercial or industrial** `TEST` quotation and order:
    - change a line's slab: it is marked "Changed from …";
    - add freight: the totals include it;
    - approvals show "GST changed on n lines".

    On a farmer (subsidised) quotation, the slab and freight controls should **not** appear.
  - **LEAD-019, Deleted leads:**
    - as Admin, Leads → Deleted leads;
    - as a state manager, there is no button, and `/leads?deleted=true` shows the live list.

**Priority 2: everything else built.** Follow the order of `Frontend/Docs/Tested-Features.md`'s sections:

- customers, ratings, the farmers' portal;
- field tracking on the web (team map, route, visits, settings);
- partner portal, search and help, documents;
- complaints, subsidy;
- schemes, rewards, payments, marketing, campaigns;
- stock, warranty, export and sample orders;
- masters, reports, dealer commission.

Each story there lists the cases that were checked against the mock. Repeat them on the real backend.

**Phone pass:** after Priority 1, repeat its 📱 cases at 360 × 780 in dark mode.

## New cases

- Add cases for anything Live-Test-Plan.md doesn't cover yet. Append them to that file as new sections, **§T onwards**, in its format: ID, Data ID, role, steps, expected.
- Expected results come from `Tested-Features.md` and `backend/docs/api/*.md`. Never invent a business rule; if unsure what should happen, mark it ⚠️ with the question.

## On every page (Live-Test-Plan "For an agent")

- **Collect errors:**
  - responses with status ≥ 400, with `x-request-id`;
  - console errors and `pageerror`;
  - any "We received data we couldn't read" (a contract mismatch: note the request).
- **Check permissions:**
  - the menu matches the role;
  - a screen the role shouldn't have says "You don't have access";
  - a dealer never sees another dealer's records. That is a **security finding**: report it first.

## Deliverables, in the PR

1. **`Frontend/Docs/Live-Test-Report.md`**, in the format of Live-Test-Plan "Deliverable 2":
   - a summary with counts;
   - issues, most serious first, each reproducible from the report alone;
   - what was blocked;
   - **test data created** (for clean-up).

   Add a short **"Ready for the client?"** verdict for each of the 13 released screens: ✅, ⚠️ or ❌, one line each.
2. **`Frontend/Docs/Tested-Features.md`:** add 🔌 to each story you checked end to end on the real backend and found working. Never add 🔌 to anything you didn't check.
3. **`Frontend/Docs/Live-Test-Plan.md`:** the new sections §T onwards.
4. **`docs/Backend-Tasks.md`:** a `BE-NNN` for each backend bug or gap, linked from the report.
5. **A changelog entry:**
   - created with `npm run changelog:new -- --type docs --data-id APP-008 --title "Live test on integration"`, or use the closest existing Data ID;
   - before pushing, run `npm run changelog:build` and `npx prettier --check .`.

**Not in this PR:** code fixes. List them in the report as "Suggested fixes", with the file you believe is at fault. The developers will pick them up.

## Done when

- Priority 1 is fully run, or each unrun case is marked ⛔ with the reason.
- The PR is open against `integration` with the report, the 🔌 marks, the new cases and any `BE-NNN`, and its CI is green.
- The PR description starts with the summary counts and the "Ready for the client?" table.
