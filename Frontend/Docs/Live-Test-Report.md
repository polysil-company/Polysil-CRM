# Live test report — 22–23 Oct 2026, https://polysil-test.pranayx.tech

- **App:** `https://polysil-test.pranayx.tech` (the staging box; the app does not show its build commit). The developers confirmed in chat that this box is the one to test, although `backend/infra/caddy/polysil-app.caddy` calls it staging.
- **API:** `https://polysil-api.pranayx.tech`. Its `/health` says `"environment":"staging"` and `"whatsapp":"11za"`: **real WhatsApp**, not the mock.
- **Run:** Playwright 1.56 with Chromium. Desktop 1440 × 900, light. Every 📱 case was repeated on a phone (360 × 780, touch, dark). Plan: [Live-Test-Plan.md](Live-Test-Plan.md) §A–§Y.
- **Logins:** `ravi` (Field Officer), `asha` (District Manager), `gujarat` (State Manager), `accounts`, `dispatch`, `quality`, `admin` (Admin-Sales), `md`. There is no Regional Manager login; MD stands in for it, but no case reached the Regional step. There is no dealer login and no partner mobile code.
- **Test mobile:** `+91 84451 69024`, given by the developers. Every `TEST` lead uses it. No OTP code was ever sent.

## Summary

- **Cases run: 146** · ✅ 121 · ⚠️ 14 · ❌ 4 · ⛔ 7 (no dealer login ×4, no scheme on staging, the BE-029 filter not deployed, and V-05, blocked by V-04)
- **Blockers for the client demo (§S): none.** §S ran end to end in one go (see the end of this report).
- **Biggest finding:** the dev API is behind `integration`. BE-023 to BE-030 are ticked Done in `docs/Backend-Tasks.md`, but none of them is deployed. Issues 1, 4, 5 and 9 come from that.

## Where each issue stands (23 Oct)

| # | Fixed by | How |
|---|---|---|
| 1 | Backend: **BE-034** | Redeploy the API from `integration` |
| 2 | Frontend: APP-009, and backend **BE-035** | Save is off until there is an item; the API should refuse it too |
| 3 | Frontend: APP-009 | Approval limits opens, read-only, to whoever may approve |
| 4 | Backend **BE-034**; frontend APP-009 | The pickers now say the list failed, with **Try again** |
| 5 | Backend: **BE-034** | — |
| 6 | Backend: **BE-036** (#206: counts follow-ups on leads only) | The card now reads "Overdue follow-ups on leads" (LEAD-020 PR) |
| 7 | Frontend: APP-009 (wording); decision **BE-038** | "Warehouse short by 500 MTR" |
| 8 | Frontend: APP-009 | A terms-only edit sends only the header |
| 9 | Backend: **BE-034** | — |
| 10 | Decision: **BE-037** (#206: the State Manager may delete leads) | The screens follow `/auth/me`; the mock now grants it too |
| 11 | Frontend: APP-009 | The first answer is highlighted; Enter opens it |
| 12 | Frontend: APP-009 | The lists fit 1280–1760 px; optional columns appear from 1536 or 1760 px |
| 13 | Frontend: APP-009 | The builder reads the freight the backend returns beside the totals |
| 14 | Frontend: APP-009 | The new lead form checks fields on the first submit, then as they change |
| 15 | Frontend: APP-009 | Ledger, credit and rating are asked for only with `payments` view |
| 16 | Frontend: APP-009 | The toast names the person as saved |
| 17 | Frontend: APP-009 | "It applies from the next refund" (or order, or discount request) |
| 18 | Frontend: APP-009 | "an Admin sales", "an MD" |
| 19 | Frontend: APP-009 | `src/app/icon.svg` |

## Issues, most serious first

| # | Case | Data ID | Role | Device | What happened | Expected | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | V-04, V-02, Y-11, Y-13, Y-14 | BE-023…BE-030 | — | — | The dev API lacks every BE-023…030 change: `GET /lookups/product-categories` and `/lookups/uoms` → 404; no `lead_id` on `GET /subsidy-applications`, no `orderable` on `GET /quotations`, no `record_type` on `GET /documents/types`, `LookupItem` without sort/quality/kind, `MeResponse` without `tasks_for_dealers` | Deployed after merge to `integration` | `/openapi.json` (296 paths); rids `c6664b4a-f8ac-4767-b6ae-6a9aba6a74af`, `eb458760-370c-4038-88f8-d91c16af9fee` |
| 2 | I-03 | QUOT-004 | Field Officer | desktop | **Save draft** works with an empty item line and saves a quotation with **no items**; that draft then offers **Send** | Save is off and says why ("Choose a product", "Enter a quantity above 0") | `POST /api/v1/quotations` → 201 with `"lines":[]`, rid `a19a01ac-ff47-458e-a246-4beb63247116`; `I-03-empty-draft-saved.jpg` |
| 3 | M-01 | APPR-002 | State Manager | desktop + phone | No **Approval limits** in the sidebar; `/approval-limits` says "You don't have access to this page" | The three ladders, read-only | `GET /api/v1/approvals/thresholds` as State Manager → **200**, rid `f5810aa5-a590-41ab-a25f-ca473985eb06`; `M-01-state-manager-no-access.jpg` |
| 4 | V-04 (→ V-05 ⛔) | MSTR-004, BE-024 | Admin | desktop | **New product**: the Category and Unit pickers open empty, with no message. Both are required, so no product can be added | Both list the backend's categories and units | `GET /lookups/product-categories` → 404 rid `f9118fda-6596-473f-bc13-fb04a1d9fb01`; `GET /lookups/uoms` → 404 rid `82696ba5-14c3-4a1d-a343-2e0c6e05af9c`; `V-04-category-unit-pickers-empty.jpg` |
| 5 | Y-13 | MSTR-009, BE-026 | Admin | desktop | Masters → Lead sources: **Order** and **Quality** read "—" on every row; **Edit** opens with both fields empty | The current values show and can be edited | `Y-13-sort-quality-empty.jpg`; not saved, to avoid blanking the scores |
| 6 | C-01 | RPT-001, TASK-001 | Field Officer | desktop | Dashboard **Overdue follow-ups = 0** ("Open tasks past their due date"), while **Tasks → My day** shows 1 overdue follow-up (due 10 Oct, 6 pm) | The same number in both places | `C-01-dashboard-overdue-0.jpg`, `C-01-tasks-1-overdue.jpg`; `GET /api/v1/dashboard/overview` → 200 |
| 7 | N-04, O-02 | SO-001, DISP-002 | any | desktop | Each order line reads "**Warehouse short: -500 MTR available**"; a dispatch from a warehouse with 0 stock goes through, and the stock goes negative | A plain shortfall ("500 MTR short"), and a decision on whether a dispatch may take stock below 0 | `N-04-warehouse-short-negative.jpg`; `POST /orders/…/dispatches` → 201, rid `90ab8736-453a-46a2-9931-acc818b08e4b` |
| 8 | I-05 | QUOT-005 | Field Officer | desktop | Editing only the **terms** also re-sends the items: History gains "Items changed · Ravi Solanki" | Only the terms are saved; History says "Customer or terms edited" only | `PATCH /quotations/40d92c44…` + `PUT /quotations/40d92c44…/lines`, both 200 |
| 9 | Y-11 | DOC-002, BE-025 | Field Officer | desktop | **Attach a file** on a lead offers all 15 types, dealer ones included (GST certificate, PAN card, Cancelled cheque, Shop photo, Shop licence) | Only the types a lead takes | `Y-11-lead-offered-dealer-document-types.jpg` (cause: issue 1) |
| 10 | Y-09 | LEAD-019 | State Manager | desktop | **Deleted leads** shows for the State Manager, and so does the deleted list | Absent, per the plan and the mock (Admin only) | Staging `GET /auth/me` gives `state_manager` leads `delete` (org_subtree). The app follows the permission correctly: **confirm which RBAC is intended** |
| 11 | B-02 | APP-001 | any | desktop | Ctrl + K → type "lead": nothing is highlighted, so **Enter does nothing** ("Dashboard" was highlighted before typing). Arrow ↓ + Enter works | Enter opens the first match | `B-02-nothing-highlighted.jpg`; the server results (`GET /api/v1/assistant?q=lead`) replace the list and the selection is lost |
| 12 | D-05, H-01 | LEAD-001, QUOT-001 | any | desktop | At 1440 px the Leads table is cut at "Follow-", and Value sits off screen; the Quotations **Total** column too | All columns fit, or a visible scroll cue | `D-05-table-clipped-at-1440.jpg` |
| 13 | Y-03 | QUOT-015 | Field Officer | desktop | The builder's Summary has no **Freight** row; freight only shows in Taxable value. The saved draft does show "Freight (GST 5%) ₹500.00" | Freight on its own row in the builder too | — (correct amounts: 2,42,927.85 + 500 = 2,43,427.85) |
| 14 | E-04 | LEAD-002 | Field Officer | desktop | **Farmer name** (focused when the dialog opens) turns red, "Enter the farmer's name.", as soon as you click another field, before typing anything | A field isn't red just for being visited | — |
| 15 | X-03 | CHNL-001 | Field Officer | desktop | A partner's page also calls `/partners/{id}/ledger`, `/credit` and `/dealer-rating` → **403** ×3; nothing shows on screen, but 3 console errors | Don't ask for what the role can't see | rids `90fc157d-a537-4f39-a330-05446a2c4bd7`, `7783e00b-893d-47fe-b60e-afb3b5b69480`, `a1a9b91a-cc05-42f0-90e4-32d47ed39317` |
| 16 | W-05 | ADMN-004 | Admin | desktop | Renaming to "TEST Person 1b" shows the toast "**TEST Person 1** saved" (the old name) | The new name | `PATCH /users/ed04204c…` `{"full_name":"TEST Person 1b"}` → 200 |
| 17 | M-03 | APPR-002 | Admin | desktop | After changing a **refund** limit the toast says "It applies from the next **order or discount request**." | Words that fit a refund ("from the next refund") | `PUT /approvals/thresholds` → 200, rid `0ab6165a-19a5-4f6c-9691-f517a3bccbdc` |
| 18 | J-03 | QUOT-007 | Field Officer | desktop | "Waiting for **a Admin sales** to approve the 25% discount" | "an Admin-Sales co-ordinator" | — |
| 19 | all | APP-001 | — | — | `/favicon.ico` → 404 on every page, and there is no `<link rel=icon>`, so the browser tab has no icon. One console error per page load | A Polysil icon | — |

## Each issue in detail

### 1. The dev API is behind `integration` (BE-023 … BE-030)
- **Seen:** `https://polysil-api.pranayx.tech/openapi.json` has 296 paths and lacks:
  - `GET /lookups/product-categories` and `GET /lookups/uoms`. Both answer 404 `{"detail":"Not Found"}`, though the route is on `integration` at `backend/api/routers/leads.py:716`. (BE-024)
  - the `lead_id` parameter on `GET /subsidy-applications`. Its parameters are only `status`, `stage`, `q`, `cursor`, `limit`. (BE-023)
  - `orderable` on `GET /quotations`. (BE-029)
  - `record_type` on `GET /documents/types`, which takes no parameters at all. (BE-025)
  - `sort_order`, `quality` and `kind` on `LookupItem`, which has only `id`, `code`, `name`, `is_active`. (BE-026)
  - `tasks_for_dealers` on `MeResponse`. (BE-030)
- **Expected:** `docs/Backend-Tasks.md` ticks all eight as Done. BE-019 says the dev API is redeployed from `integration` after each backend merge.
- **Effect on screens:** issues 4, 5, 9; the empty Category filter on Products (V-02); and Y-14, which can't be checked.
- **Likely layer:** deployment. Redeploy the dev API from the current `integration`, then re-run V-02, V-04, V-05, Y-10…Y-15.

### 2. I-03: a quotation draft can be saved with no items
- **Steps:**
  1. Sign in as Field Officer.
  2. Open a Qualified lead → **New quotation**.
  3. Don't pick a product or a quantity → **Save draft**.
- **Seen:**
  - Save is enabled, and the toast says "Draft saved · TEST Claude 1 · Draft".
  - The draft reads "Items (0) · No items yet. This draft is empty.", total ₹0.00, and offers **Send**.
  - The same happened twice: drafts `df4e3bcb…` and `40d92c44…`.
- **Expected:** Save is off with a reason, as the **order** builder does. New order shows "Add at least one item." and keeps Save off.
- **Request:** `POST /api/v1/quotations` → 201, x-request-id `a19a01ac-ff47-458e-a246-4beb63247116`, body `{"lead_id":"b2ac8f92-…","sales_type":"commercial",…,"lines":[]}`.
- **Likely layer:** both. The frontend form lets an empty line through. The backend accepts `lines: []`.

### 3. M-01: the State Manager can't read the approval limits
- **Steps:**
  1. Sign in as `gujarat@polysil.in` (State Manager).
  2. Look for Admin → Approval limits: it isn't in the sidebar.
  3. Open `/approval-limits`.
- **Seen:** "You don't have access to this page · Ask your manager or an admin if you need it." The same on desktop and on a phone.
- **Expected:** the three ladders, read-only, with "Only an administrator changes these."
- **Request:** `GET /api/v1/approvals/thresholds` with the State Manager's token → **200** and all 11 rows. x-request-id `f5810aa5-a590-41ab-a25f-ca473985eb06`.
- **Likely layer:** frontend permission gate. `src/components/layout/navigation.ts:427-436` gates the page on module `masters`, which the State Manager lacks. The backend serves the data to that role.

### 4. V-04: the Category and Unit pickers are empty
- **Steps:**
  1. Sign in as Admin.
  2. Admin → Products & prices → **New product**.
  3. Open **Category**, then **Unit**.
- **Seen:** both lists open empty, with no "couldn't load" message. Submitting says "Choose its category." / "Choose its unit.", so a product can't be added (V-05 ⛔). On the list page the Category filter says "No categories yet."
- **Requests:** `GET /api/v1/lookups/product-categories` → 404, rids `f9118fda-6596-473f-bc13-fb04a1d9fb01` and `c396b3e9-7f80-48d7-89b3-6ff584948584`. `GET /api/v1/lookups/uoms` → 404, rid `82696ba5-14c3-4a1d-a343-2e0c6e05af9c`.
- **Console:** `Failed to load resource: the server responded with a status of 404 ()` ×3.
- **Likely layer:** backend deployment (issue 1). The frontend also shows nothing when the lookup fails: per AGENTS.md §6 it should show an error state with a reference.

### 5. Y-13: Masters show no sort order or quality
- **Steps:**
  1. Sign in as Admin.
  2. Admin → Masters → Lead sources.
  3. Press **Edit** on WhatsApp.
- **Seen:** the Order and Quality columns read "—" on all 9 rows. The edit dialog has **Sort order** and **Quality** fields, both empty.
- **Expected:** the real values, editable. Quality counts in the lead score.
- **Likely layer:** backend deployment (BE-026). Risk: saving an edit now might blank those values. Not tried.

### 6. C-01: the dashboard's overdue count disagrees with Tasks
- **Steps:**
  1. Sign in as `ravi@polysil.in`.
  2. Read the Dashboard card "Overdue follow-ups".
  3. Open Tasks → My day.
- **Seen:**
  - The dashboard says **0** · "Open tasks past their due date".
  - Tasks says "0 due today · **1 overdue from earlier**": *TEST walk 10oct task for ravi*, Follow-up, due 10 Oct 6:00 pm, given by Asha Patel.
  - Asha's **Team** view shows Ravi with "Overdue 1".
- **Request:** `GET /api/v1/dashboard/overview` → 200. The figure comes from the backend.
- **Likely layer:** backend (the overview's overdue count), unless the card is meant to count something narrower. If so, the label should say what.

### 7. N-04 / O-02: negative warehouse stock
- **Seen:**
  - Before submit: "Warehouse short: 0 MTR available".
  - After submit: "Warehouse short: -500 MTR available" and "-1000 NOS. available".
  - Dispatch D/SO/GJ/2026-27/00013/1 (200 MTR) was recorded from "Main warehouse" with no stock.
- **Note:** the order form says "a shortfall warns and never blocks the order". So the shortfall may be by design, but "-500 available" reads badly. Confirm with the client whether a dispatch may go out without stock.
- **Likely layer:** wording in the frontend; a business rule for the backend or client.

### 8. I-05: a terms-only edit is recorded as "Items changed"
- **Steps:** on a draft → Edit draft → change only **Terms** → Save changes.
- **Requests:** `PATCH /quotations/40d92c44-96c9-4f42-92cc-2e7c1da5807d` (party and terms) and `PUT …/lines` (the unchanged lines). Both 200.
- **Seen:** History: "Items changed · Ravi Solanki", "Customer or terms edited · Ravi Solanki".
- **Likely layer:** frontend (sends the lines when they haven't changed).

### 9–19
The table above has the full detail for each. 9 comes from issue 1. 10 is a question about RBAC. 11–19 are small frontend fixes.

### Other things noticed (no case failed)
- **Two stuck orders:**
  - SO/GJ/2026-27/00005 waits in Admin's and the State Manager's inbox with "**No District Manager to decide**", raised 3 weeks ago.
  - SO/GJ/2026-27/00010 is "Waiting on **Regional Manager**" since 9 Oct.
  - There is no Regional Manager login in the list we were given, so nobody may be able to approve it.
- **"Lead not visible":** three of Ravi's own quotations show this (Draft "TEST walk 1", QT 00002, QT 00003), because their leads are deleted (00076–00078, seen in Deleted leads). Consider showing "Lead deleted".
- **Sessions pile up:** Admin's own page shows "Live sessions: **437 devices**". Sessions may never be pruned.
- **Duplicate names:** two distributors are both named "Saurashtra Agro Distributors" (DIST-SAU and DEMO-DIST).
- **Lists without a total:** Users & roles and Channel partners say "Newest first." with no total. The plan expects a count.
- **Plan out of date:**
  - **U-06:** a dealer's QR code no longer shows "Enquiry through …", by design (F-19: the code's label is for staff).
  - **E-06:** land is now entered in **hectares**, with acres shown alongside.
  - **N-02:** the Place order form comes pre-filled (Commercial, the lead's place, Full payment).
- A **won** lead still offers **New quotation**.

## Blocked
- **A-04, Q-05, X-08, Y-15:** no dealer login and no partner mobile code (OTP codes were not sent).
- **V-05:** blocked by V-04. No category or unit can be chosen, so no product can be added.
- **Y-12:** staging has no scheme ("No schemes yet").
- **Y-14:** **New order** from a lead opens the typed-in order form with no quotation picker. The BE-029 `orderable` filter is not deployed either (issue 1).

## Test data created (to clean up)
All are on the test mobile `+91 84451 69024` or marked TEST.
- **Leads:**
  - TEST Claude 1, POL/GJ/2026-27/00101: Commercial, now Won.
  - TEST Claude 2, POL/GJ/2026-27/00102: Subsidised, now Qualified. Lost and reopened once; reassigned to Mehul and back; partner Shah Irrigation.
  - TEST Demo Farmer, POL/GJ/2026-27/00103: Won (§S).
- **Quotations:**
  - QT/GJ/2026-27/00017 v1 (replaced) and v2 (Accepted).
  - QT/GJ/2026-27/00018 (Accepted, §S).
  - Drafts `34ae80b3…` and `df4e3bcb…` were **deleted** in J-09.
- **Sales orders:**
  - SO/GJ/2026-27/00013: Closed short. Dispatch D/…/00013/1 voided.
  - SO/GJ/2026-27/00014: Cancelled.
  - SO/GJ/2026-27/00015: Dispatched, D/…/00015/1 and /2 (§S).
- **Tasks:**
  - TEST call (cancelled).
  - TEST visit about this lead.
  - TEST send revised layout (from minutes `4595c22e…`).
  - By a script mistake, *TEST walk 10oct task for ravi* (an older test task) was marked done and **reopened at once**. It is Overdue again, with a done + reopen pair in its history.
- **Messages:**
  - Ravi → Mehul "TEST hello from the live test".
  - Ravi → Asha "TEST: please look at this lead" (with lead 00101).
  - Asha's notifications were all marked read (P-03).
- **QR code:** TEST QR 1b (`MSUSRU`), On, dealer Shree Ganesh Agro Agency.
- **Users:** TEST Person 1b (`test.person1@polysil.in`), Field Officer, **deactivated**.
- **Channel partners:** TEST Dealer 1 (`TEST-DLR-1`), open, payment terms 30 days.
- **Marketing:** MM/GJ/2026-27/00001 (1 Polysil pen, ₹15), approved and dispatched.
- **Approval limits:** the State Manager refund limit was changed to ₹1,50,000 and **put back to ₹1,00,000** (M-03).
- **WhatsApp:** creating the 3 leads queued 3 acknowledgements to the test mobile. The approved orders' "customer is told" messages went to it too. No quotation was sent on WhatsApp ("Don't send a message" every time).

## All results

| Section | ✅ | ⚠️ | ❌ | ⛔ | Notes |
|---|---|---|---|---|---|
| A Sign-in (7) | 6 | | | 1 | A-03 checked with a Caps Lock key event (headless Chromium can't toggle the real key). A-04 ⛔ |
| B Navigation (4) | 3 | 1 | | | B-02 ⚠️. Sidebars per role below |
| C Dashboard (2) | 1 | 1 | | | C-01 ⚠️ (issue 6) |
| D Leads list (7) | 6 | 1 | | | D-05 ⚠️ (issue 12) |
| E New lead (6) | 5 | 1 | | | E-04 ⚠️ (issue 14) |
| F Lead page (3) | 3 | | | | |
| G History, stage, assign (8) | 8 | | | | |
| H Quotations reading (5) | 5 | | | | |
| I Making a draft (5) | 3 | 1 | 1 | | I-03 ❌, I-05 ⚠️ |
| J Send, approve, answer, revise, delete (9) | 8 | 1 | | | J-03 ⚠️ wording |
| K Customer link (3) | 3 | | | | |
| L Approvals inbox (5) | 5 | | | | |
| M Approval limits (3) | 1 | 1 | 1 | | M-01 ❌, M-03 ⚠️ |
| N Sales orders (8) | 7 | 1 | | | N-04 ⚠️ |
| O Dispatch (5) | 5 | | | | |
| P Notifications (4) | 4 | | | | |
| Q Messages (5) | 4 | | | 1 | Q-05 ⛔ |
| S Whole story (1) | 1 | | | | |
| T Tasks (11) | 11 | | | | |
| U QR codes, enquiry page (6) | 6 | | | | |
| V Products and prices (9) | 6 | 1 | 1 | 1 | V-02 ⚠️, V-04 ❌, V-05 ⛔ |
| W Users and roles (6) | 5 | 1 | | | W-05 ⚠️ |
| X Channel partners (8) | 6 | 1 | | 1 | X-03 ⚠️, X-08 ⛔ |
| Y 22 Oct merges (16) | 9 | 3 | 1 | 3 | Y-03, Y-09, Y-11 ⚠️; Y-13 ❌; Y-12, Y-14, Y-15 ⛔ |
| **Total (146)** | **121** | **14** | **4** | **7** | |

**What each role sees in the sidebar (B-01).** No item is greyed "Soon"; every item opens.

| Role | Sidebar |
|---|---|
| Field Officer | Dashboard, Messages, Help · Leads, Customers, Quotations, Sales orders, QR codes, Subsidy, Targets, Team map, Visits · Complaints, Ratings, Tasks · Channel partners, Marketing material, Schemes, Rewards · Dispatch queue, Stock · Reports, Complaint targets, Products & prices |
| District / State Manager | The above, plus Approvals, Accounts queue, Receipts, Dealer commissions, Users & roles. No **Approval limits** (issue 3) |
| Accounts | Leads, Customers, Quotations, Sales orders, QR codes, Approvals, Subsidy · Complaints, Ratings, Tasks · Accounts queue, Receipts, Dealer commissions, Dispatch queue, Stock · Reports, Complaint targets, Users & roles |
| Dispatch | Sales orders, Approvals · Ratings, Tasks · Dispatch queue, Stock · Reports, Users & roles |
| QC Manager | Complaints, Tasks · Stock · Reports, Complaint targets. The dashboard says "Nothing to report yet" |
| Admin, MD | Everything, including Approval limits, Campaigns, Subsidy masters, Masters, Company settings, Tracking settings |

**Phone pass (360 × 780, dark).** No page scrolls sideways: Dashboard, Leads, a lead, Quotations, a quotation, the quotation builder, Sales orders, an order, Approvals, Messages, Tasks, QR codes, Products, Channel partners, Users, Approval limits, the enquiry form, the customer link. On a phone the Leads / Customers / Quotations / Sales orders tab row is cut at "Sales orde"; it scrolls sideways.

**§S timings** (one continuous run; each step includes about 6 s of sign-in):

| Step | Time |
|---|---|
| Lead created, contacted, qualified | 27 s |
| Quotation at 8%, approval asked | 18 s |
| District Manager's bell → approve | 16 s |
| Sent without a message | 16 s |
| Customer link, signed out | 4 s |
| Accepted → Won → order → submitted | 34 s |
| District → Accounts → Dispatch approved | 46 s |
| Officer's bell | 8 s |
| Dispatched in two parts | 25 s |

The lead's Activity lists all 18 events in order.
