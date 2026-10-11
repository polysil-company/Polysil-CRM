# Live test plan: the CRM on the real backend

A complete, self-contained plan for testing the hosted app (the `integration` branch, connected to the backend's dev API) by hand or by an agent driving a browser. It produces two documents:

1. **A client walkthrough** (`Docs/Client-Feature-Walkthrough.md`), in plain words for a non-technical reader who knows the business: per functionality, what works, what doesn't, what isn't built yet, and how to try it.
2. **An issue report** (`Docs/Live-Test-Report.md`) for the developers: only what failed, each with enough evidence to find the cause in minutes.

The plan covers everything built so far ([Tested-Features.md](Tested-Features.md) lists the same stories with their automated checks). Each case has an ID (`L-03`), the Data ID of the functionality (`LEAD-002`), the role to use, the steps and what should happen.

---

## 0. Before you start

### 0.1 What you need

| Input | Where it comes from |
| --- | --- |
| `APP_URL`: the hosted frontend | the developers |
| One login per role (§0.3) | the developers, as environment secrets or in the chat. **Never** write a password into any file, screenshot, report or commit. |
| A test mobile number you may send WhatsApp messages to | the developers. Without one, never press "Send on WhatsApp" (§0.2). |
| A browser | Playwright with Chromium (`executablePath: /opt/pw-browsers/chromium` in the cloud container), or any desktop browser by hand |

If the network refuses `APP_URL` or the API host, stop and ask for them to be allowed. Do not test against anything else.

### 0.2 Rules: this is a shared database with real-looking data

- **Name everything you create `TEST …`**: farmer names `TEST Ramesh Patel`, remarks `TEST: …`, notes `TEST note …`. That makes test records easy to find and clean up.
- **Use only the test mobile number** for anything you create. Never message, call or share a link with a real customer's number.
- **Never press "Send on WhatsApp"** unless the party's mobile is the test number. Use the option that sends without a message.
- **Approval limits:** change a limit only in case M-03, and put it back to the exact old value straight after.
- **Never delete or cancel a record you didn't create.** Only an order or quotation you made in this run may be cancelled or deleted.
- **Don't fix, retry endlessly, or work around.** If something fails twice the same way, record it (§0.6) and move on.
- **Stop** and report if you see another person's personal data where it shouldn't be (e.g. a dealer seeing other dealers' leads). That is a security finding.

### 0.3 Roles

The app shows a different sidebar and different buttons per role. Test each case as the role named. "Field Officer" in this plan is the **Employee** role in the app.

| Role in this plan | Role code | What they do |
| --- | --- | --- |
| Field Officer | `employee` | Captures and works their own leads; makes quotations and orders |
| District Manager | `district_manager` | Their district's leads; approves orders and discounts up to their limit |
| State Manager | `state_manager` | The state's leads; approves above District |
| Regional Manager | `regional_manager` | Top manager; approves anything above State |
| Accounts | `account_manager` | Checks payment on every order before Dispatch; a remark is always required |
| Dispatch | `dispatch_manager` | Final order approval; records, voids and closes dispatches |
| Admin | `admin` | Everything, including approval limits |
| Dealer / Distributor / Sub-dealer | partner roles | Sign in with a mobile code; see their own channel's records only |

If a login is missing, test what you can and mark the rest **Blocked: no login for <role>**.

### 0.4 Two screen sizes

Run every case on a **desktop** (1440 × 900). Then repeat the cases marked **📱** on a **phone** (360 × 780), in **dark mode** for at least one pass. On a phone the sidebar is behind the menu button (☰).

### 0.5 What every result is

| Result | Means |
| --- | --- |
| ✅ **Works** | Did exactly what "Expected" says |
| ⚠️ **Works with a problem** | The job gets done, but something is wrong: wrong text, a figure looks off, slow (> 5 s), layout broken on a phone, a confusing message |
| ❌ **Doesn't work** | The job can't be done: an error page, nothing happens, wrong data saved, a button missing that should be there |
| 🚧 **Not built yet** | The app says "Soon", or §R lists it |
| ⛔ **Blocked** | Couldn't test: no login, no suitable record, an earlier step failed |

### 0.6 Evidence for every ⚠️ and ❌

Capture all of it. It is what lets a developer fix it without asking you.

1. **Screenshot**, JPEG: `Docs/screenshots/live-test/<case-id>-<what>.jpg`, e.g. `M-01-error.jpg`. No passwords on screen.
2. **The REF code** if the app shows an error box: `REF APPR-002 · 06a3e68e-…`. Copy it exactly. The developers trace it in the logs.
3. **The failing request** from the browser's network log: method, path, status, and its `x-request-id` header. For example: `GET /api/v1/approvals/thresholds → 200, but the screen said it couldn't read it`. With Playwright, listen to `page.on("response")` and keep every response with status ≥ 400. Also keep any request whose page shows "We received data we couldn't read": that one is a **contract** problem, where the backend's answer doesn't match the screen.
4. **Console errors** (`page.on("console")` of type `error`, and `page.on("pageerror")`).
5. **Steps to reproduce**, numbered, from sign-in.

What the app's error screens mean (this tells the developer where to look):

| The screen says | Usually means |
| --- | --- |
| "We received data we couldn't read" + REF | The backend answered in a shape the frontend doesn't expect: frontend schema or backend contract |
| "You don't have access" / a 403 | The role lacks a permission. Check it should have it (§0.3) |
| "Not found" for a record you just saw | Scope: the role can't see it, or a wrong link |
| "Something went wrong" + REF, or a 5xx | Backend error |
| A toast with a reason ("The quotation has moved on") | Expected: someone else changed it. Not a bug unless you were alone |

---

## A. Sign-in and session

| ID | Data ID | Role | Steps | Expected |
| --- | --- | --- | --- | --- |
| A-01 📱 | AUTH-003 | Any staff | Open `APP_URL` → **Staff email** → enter work email and password → **Sign in** | Lands on the Dashboard. The top bar shows your initials. |
| A-02 | AUTH-003 | Any staff | Sign in with the right email and a wrong password | A clear message; the email stays, the password clears. No REF error. |
| A-03 | AUTH-003 | — | Type the password with Caps Lock on | A Caps Lock warning shows. |
| A-04 📱 | AUTH-001 | Dealer | **Mobile** sign-in → **Mobile number** → **Send code** → enter the code → **Verify and sign in** | Signed in as the partner. The sidebar shows only partner items (no Approvals, no Admin). |
| A-05 | AUTH-004 | Any | Signed in, reload the page | Still signed in, on the same page. |
| A-06 | AUTH-006 | Any | Signed out, open `APP_URL/leads` directly | Sent to sign-in. After signing in, lands on Leads (not the Dashboard). |
| A-07 | AUTH-005 | Any | Open two tabs → sign out in one (account menu → Sign out) | Both tabs go to sign-in. No toast from before stays on screen. |

## B. Navigation per role

| ID | Data ID | Role | Steps | Expected |
| --- | --- | --- | --- | --- |
| B-01 | APP-001 | Each role in turn | Sign in and list the sidebar items | Matches §B table below. Items marked **Soon** are greyed and can't be opened. |
| B-02 | APP-001 | Any staff | Press Ctrl + K (⌘ + K on Mac) → type "lead" → Enter | The command menu opens, finds Leads, opens it. Esc closes it. |
| B-03 | APP-005 | Any | Desktop: press Ctrl + B | The sidebar collapses to icons and back. |
| B-04 📱 | APP-002 | Any | Toggle the theme (sun/moon in the top bar) | Light ↔ dark; everything stays readable. |

**Expected sidebar (built items):**

| Item | Field Officer | District / State / Regional | Accounts | Dispatch | Admin | Partner |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard, Messages | ✓ | ✓ | ✓ | ✓ | ✓ | Dashboard only |
| Leads, Quotations | ✓ | ✓ | if permitted | if permitted | ✓ | their own channel's |
| Sales orders | ✓ | ✓ | ✓ | ✓ | ✓ | their own |
| Approvals | — | ✓ | ✓ | ✓ | ✓ | — |
| Approval limits | read-only for anyone who can open it | | | | ✓ (can change) | — |

Record what each role actually sees. The backend's permissions decide, so a difference is a finding to report, not necessarily a bug.

## C. Dashboard (RPT-001)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| C-01 📱 | Field Officer, then State Manager | Open Dashboard | Four figures: open pipeline value (₹), new leads, conversion %, overdue follow-ups. Each has a change and a small trend where available. Pipeline by stage with counts and ₹; leads by source; the next follow-ups, overdue ones marked. No error box. |
| C-02 | Field Officer vs State Manager | Compare the numbers | The manager sees as much or more than the officer (a wider area). |

## D. Leads: the list (LEAD-001, LEAD-004)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| D-01 📱 | Field Officer | Sales → Leads | A table with "1–25 of N". The Leads tab and the sidebar show the same total. |
| D-02 | Any | Type part of a farmer's name, then part of a mobile, then an exact inquiry number (`POL/GJ/…`) | Each finds the matching lead(s). |
| D-03 | Any | **Stage** filter → read the options → tick Qualified and Negotiation | Every stage has a one-line explanation under it. The list shows only those two stages. The URL changes; reload keeps the filter. |
| D-04 | Any | **Source** filter, then **Type** filter | Single choice each; the list narrows. **Clear** removes the filter. |
| D-05 | Any | Click the **Customer** header, then **Value** | Sorted A→Z, then by value. Clicking again reverses. From page 2, sorting returns to page 1. |
| D-06 | Any | Next page → copy the URL → open it in a new tab | The same page opens. |
| D-07 | Any | Filter to something that can't match (search `zzzz`) | "No leads match these filters" with **Clear filters**. |

## E. Leads: creating one (LEAD-002)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| E-01 📱 | Field Officer | Leads → **New lead** → Farmer name `TEST <your name> 1`, Mobile = the test number, Territory: type a taluka name and pick it, Inquiry type, Irrigation system, Crops (pick 2), Land `4.5` → **Create lead** | A toast "Lead created". The new lead is at the top of the list with its inquiry number. |
| E-02 | Field Officer | New lead → type the state's name ("Gujarat") in Territory | The state is **not** offered: "No place matches". Districts, talukas and villages are. |
| E-03 | Field Officer | New lead → leave everything empty → **Create lead** | Each required field says what's missing, in red, on the field itself. |
| E-04 | Field Officer | Open a dropdown (Inquiry type) and close it without choosing | It is **not** marked red just for being opened. |
| E-05 | Field Officer | Create a second lead with the **same mobile** as E-01 | Created, with a toast naming the possible duplicate. |
| E-06 | Field Officer | Land `abc`, or 11 crops | A field error ("Enter the land in acres, e.g. 4.5." / at most 10 crops). |

## F. Leads: one lead's page (LEAD-003)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| F-01 📱 | Field Officer | Open the lead from E-01 | Name, stage badge, priority (Hot/Warm/Cold while open), Call and WhatsApp buttons, contact, territory, owner, crops as tags, land in acres, created date. Activity at the bottom. |
| F-02 | Field Officer | Open the lead from E-05 | Shows the possible duplicate with how it matched (mobile). |
| F-03 | Any | Open a **won** lead | No priority badge; no Update stage. |

## G. Leads: history, notes, stage, assign (LEAD-005 … 008)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| G-01 📱 | Field Officer | On the E-01 lead: type a note `TEST note` in Activity → Ctrl + Enter | The note appears at the top at once, with your name. |
| G-02 | Field Officer | **Update stage** → read the menu → **Mark as contacted** | The menu explains the current stage and each move. The stage becomes Contacted; the history says "<you> moved the lead from New to Contacted". |
| G-03 | Field Officer | Update stage → **Mark as qualified** | Qualified. "Quoted" shows greyed: "Happens when a quotation is sent". |
| G-04 | Field Officer | On the E-05 lead: Update stage → **Mark as lost…** → submit without a reason, then choose a reason → confirm | It first asks for the reason. Then Lost, with the reason in the history. |
| G-05 | Field Officer | On the lost lead: **Reopen lead…** → confirm | Back at the stage it was lost from. The history says so. |
| G-06 | District Manager | On a lead in your district: **Assign** → change the owner to a colleague, and the channel partner to a dealer → Save | Saved; the page shows the new owner and partner. The history reads "assigned the lead to <name> and made <dealer> the channel partner". |
| G-07 | Field Officer | Open Assign | The owner can't be changed by an employee (it says only a manager can); the partner can. |
| G-08 | Any | On a lead with long history: **Show older activity** | Older events load below; nothing already shown disappears. |

## H. Quotations: reading (QUOT-001 … 003)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| H-01 📱 | Field Officer | Sales → Quotations | Number (or "Draft"), version, lead, party, status chip, type, owner, dates, total. A draft waiting on a manager reads **Awaiting approval**. |
| H-02 | Any | Status filter (several), Type filter, search by number / name / mobile, **Show older versions** | Each narrows the list; replaced versions read "Superseded by v2". |
| H-03 📱 | Any | Open a **sent** quotation | Items with discounts, taxable value, GST (CGST + SGST or IGST), totals; party; terms; the customer link with **Copy**; history; versions. |
| H-04 | Any | **Open PDF** | The PDF opens in a new tab. While it's being made: "Preparing PDF…", then it becomes available by itself. |
| H-05 | Any | On a lead with quotations | The lead page lists every version, older ones muted. |

## I. Quotations: making a draft (QUOT-004, QUOT-005, MSTR-003)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| I-01 | Field Officer | On a **New** or **Contacted** lead: New quotation | Refused with a reason ("Qualify the lead first"). |
| I-02 📱 | Field Officer | On the Qualified E-01 lead: **New quotation** → add 2 items (type a product name, pick it, quantity) → give one item a 3 % discount | When typing pauses, each line shows the rate, taxable value, GST and total. "Indicative rate" shows where the price is a stand-in. Old figures dim while new ones load. |
| I-03 | Field Officer | Leave an item without a product or quantity | Save is off and says why ("Choose a product", "Enter a quantity above 0"). |
| I-04 | Field Officer | Save the draft | The draft opens with the **same** totals as the builder showed. |
| I-05 | Field Officer | On the draft: Edit → change the terms → Save | Saved; only that changed. |

## J. Quotations: send, discount approval, answer, revise, delete (QUOT-006 … 011)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| J-01 | Field Officer | On the I-04 draft (discount within your limit): **Send** → choose to send **without** a WhatsApp message (unless the party's mobile is the test number) | It gets a number (`QT/GJ/…`) and 45 days' validity. The lead moves to **Quoted**. "Preparing PDF…" then Open PDF. |
| J-02 | Field Officer | Make a second draft with a large discount (e.g. 25 %) → Save | A notice says the discount needs approval, with your limit. Send is off. **Ask for approval** takes a reason. |
| J-03 | Field Officer | Ask for approval with reason `TEST: matching a competitor` | "Waiting for a <role> to approve…". The list shows **Awaiting approval**. |
| J-04 | the approving manager | Approvals → find it → **Approve** | It leaves the inbox. Back as the officer: "Discount approved" and **Send** is on. |
| J-05 | Field Officer + manager | Repeat J-02/J-03 on another draft; the manager **Rejects** with a reason | The officer's draft shows the reason. |
| J-06 | Field Officer | On the sent J-01 quotation: record the customer's answer **In negotiation** with `TEST: wants 2 % more` | Status In negotiation; the lead moves to Negotiation. |
| J-07 | Field Officer | **Revise into version 2** | A v2 draft at today's prices opens. Sending it marks v1 "Superseded by v2"; same number. |
| J-08 | Field Officer | Send v2, then record **Accepted** | Accepted; the lead becomes **Won**. **Place order** appears (§N). |
| J-09 | Admin | Delete a **draft** you made | Gone; back on the lead. A sent quotation has no Delete. |

## K. The customer's quotation link (QUOT-012)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| K-01 📱 | — (signed out, private window) | Copy the customer link from a sent quotation (H-03) and open it | Without signing in: number, from whom, total incl. GST, item count, sent date, valid until, **View quotation**. No phone numbers or addresses shown. |
| K-02 | — | **View quotation** | The PDF opens. |
| K-03 | — | Change one character of the link | "This link doesn't open a quotation", with what to do. |

## L. Approvals inbox (APPR-001)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| L-01 📱 | District Manager | Approvals | What waits on you, oldest first: discounts and orders side by side, the party, total, discount asked, who raised it, how long it has waited. The sidebar count matches. |
| L-02 | District Manager | **Reject** without a reason | Refused: "Say why. The person who asked reads it." |
| L-03 | State Manager | **Include steps below me** | Lower managers' steps added, each marked whose it is. |
| L-04 | Accounts | Approve an order step without a remark | Refused: Accounts must note the payment check. With a remark it goes through. |
| L-05 | Field Officer | Look for Approvals | Not in the sidebar. |

## M. Approval limits (APPR-002)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| M-01 📱 | State Manager | Admin → Approval limits | Three ladders, read-only: **Order value** (District, State, Regional, incl. GST), **Discount on a quotation** (Field Officer → Admin-Sales, in %), **Refund on a complaint** (District, State, Regional, ₹). "Only an administrator changes these." No error box. |
| M-02 | Admin | Same page | Each level has a change button. |
| M-03 | Admin | Change the State Manager **refund** limit to something below District's → Save; then to a valid value → Save; **then put the old value back** | The first is refused on the field (must be above the level below). The second saves and the ladder updates at once. Restore the original value. |

## N. Sales orders (SO-001 … 004)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| N-01 📱 | Field Officer | Sales → Sales orders | Number (or "Draft order"), dealer or "Direct sale", party, status with whom it waits on ("Waiting on Accounts"), shipped share, type, owner, total. Filters and "Only my orders" kept in the URL. |
| N-02 | Field Officer | On the accepted J-08 quotation: **Place order** → type, delivery address, payment terms, remarks `TEST order` → **Make draft order** | The draft order opens with the quotation's lines and totals. The quotation now shows **Open order**. |
| N-03 | Field Officer | On the draft: change delivery and remarks → Save | Saved. |
| N-04 | Field Officer | **Submit** for approval | It gets a number (`SO/GJ/…`) and "Waiting for approval". The approval chain lists the managers by value, then Accounts, then Dispatch. |
| N-05 | each approver in turn | Approvals → approve the N-04 order (District → … → Accounts with a remark → Dispatch) | After each step the next role sees it. At the end: **Approved**; **Open PDF** appears. The history lists every step with names. |
| N-06 | Field Officer + manager | On another order, the manager **rejects** with a reason | The order returns to draft with the reason; the officer can edit and **Submit again**. |
| N-07 | Field Officer | Cancel an order you created (draft or waiting) with reason `TEST cancel` | Cancelled, with the reason shown. |
| N-08 📱 | Any | Open an approved order; scroll to the bottom | Lines with ordered / sent / open; totals; approval chain; dispatches; history. There is space below the last card. |

## O. Dispatch (DISP-002)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| O-01 | Dispatch | On the approved N-05 order: record a dispatch → quantity more than open → submit | Refused on the field. |
| O-02 | Dispatch | Record a dispatch of part of the items, with challan, invoice `TEST-INV-1`, transporter, vehicle | Status **Partly dispatched**; the dispatch is listed (`D/SO/…/1`); open quantities drop. |
| O-03 | Dispatch | **Void** that dispatch with reason `TEST void` | It stays listed, struck through; quantities are open again. |
| O-04 | Dispatch | Close the rest short with reason `TEST close` | **Closed short**, with the reason. |
| O-05 | District Manager | Open the same order | No dispatch buttons. |

## P. Notifications (NOTIF-001, NOTIF-002)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| P-01 📱 | the manager from J-03 | Open the bell (top bar) | A badge with the unread count. The list shows "A discount … needs your approval" with an icon. |
| P-02 | same | Click that notification | The quotation opens; that notification is no longer unread; the badge drops by one. |
| P-03 | same | **Mark all as read** | The badge disappears. |
| P-04 | Field Officer | After N-05, open the bell | "Sales order … was approved"; clicking opens the order. |

## Q. Messages (MSG-001 … 005)

| ID | Role | Steps | Expected |
| --- | --- | --- | --- |
| Q-01 📱 | Field Officer | Messages → New conversation → search a colleague → pick them | The thread opens with their name and "Say hello to <name>". |
| Q-02 | Field Officer | Type `TEST hello` → Enter | The message appears; the conversation now shows in the list. |
| Q-03 | the colleague | Open Messages | An unread count on the conversation and in the sidebar. Opening it clears the count. |
| Q-04 | Field Officer | On a lead: **Share with a colleague** → pick the colleague → send | The message links the lead by its inquiry number; clicking it opens the lead. |
| Q-05 | Dealer | Open `APP_URL/messages` | "Messages are for Polysil staff". |

## R. Not built yet: confirm they show as "Soon", and list them as 🚧

These are planned and the backend serves most of them. The app has no screens for them yet. In the client walkthrough, list each under **Not built yet** with one line on what it will do. Don't test them.

- **Tasks and follow-ups**: daily follow-up calls and visits, the planner, meeting minutes.
- **Complaints**: registering a complaint, the quality check, refunds and replacements (refund **limits** already show in M-01).
- **Subsidy applications.**
- **Direct orders**: typed in line by line, not from a quotation; a combined order for one dealer.
- **Editing or deleting a lead, the duplicates queue, merging duplicates.**
- **Lead QR codes and the public enquiry form.**
- **Channel partners, schemes, marketing, reports.**
- **Admin masters**: products, price lists, tax rates, users and roles, offices, territories.

## S. The whole story in one run (the client demo)

Run this last, as one continuous flow. It is the demo the client will recognise. Note the time each step takes.

1. Field Officer creates `TEST Demo Farmer` (E-01) → marks Contacted, then Qualified (G-02, G-03).
2. Makes a quotation with a discount above their limit (I-02, J-02) → asks for approval (J-03).
3. The District (or State) Manager gets the bell notification (P-01) → approves in the inbox (J-04).
4. The officer sends the quotation without WhatsApp (J-01) → opens the customer link signed out (K-01).
5. Records **Accepted** (J-08) → the lead is Won → **Place order** (N-02) → **Submit** (N-04).
6. Each approver approves in turn, Accounts with a remark (N-05). The officer gets "approved" (P-04).
7. Dispatch records a partial dispatch (O-02), then the rest.
8. The lead's Activity tells the whole story in order (G-08).

---

## Deliverable 1: the client walkthrough

File: `Docs/Client-Feature-Walkthrough.md`. Plain words, no codes, no developer terms (no "API", "contract", "403", "REF"). One section per functionality, in this exact shape:

```markdown
## Leads: capturing a new enquiry

**What it's for:** every enquiry, from WhatsApp, the website, QR codes or a field visit, in one list, so nobody is missed.

**Works**
- Create a lead with the farmer's name, mobile, place, crops and land.
- The app warns when the same farmer may already be in the list.

**Works, with a problem**
- Searching by mobile number is slow (about 6 seconds).

**Doesn't work yet**
- Choosing a village in the place picker shows an error.

**Not built yet**
- Follow-up dates on a lead (they come with Tasks).

**How to try it**
1. Sign in → **Sales** → **Leads** → **New lead**.
2. Fill in the farmer's name and mobile, pick the place, crops and land.
3. Press **Create lead**: the lead appears at the top of the list.
```

Sections, in this order: Signing in · Getting around · Dashboard · Leads: the list · Leads: capturing an enquiry · Leads: working a lead (notes, stages, assigning) · Quotations: making one · Quotations: discount approval · Quotations: sending and the customer's link · Quotations: the customer's answer and new versions · Approvals · Approval limits · Sales orders · Dispatch · Notifications · Messages · Not built yet. End with **The whole story** (§S) as numbered steps.

## Deliverable 2: the issue report

File: `Docs/Live-Test-Report.md`. For the developers. Short, and with every claim backed by evidence.

```markdown
# Live test report — <date>, <APP_URL>, integration @ <commit if shown>

## Summary
- Cases run: 96 · ✅ 80 · ⚠️ 7 · ❌ 5 · ⛔ 4 (no Dispatch login)
- Blockers for the client demo (§S): <list the case IDs, or "none">

## Issues, most serious first
| # | Case | Data ID | Role | Device | What happened | Expected | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | M-01 | APPR-002 | State Manager | desktop | Error box "We received data we couldn't read" | Three ladders | REF APPR-002 · 06a3e68e…; GET /api/v1/approvals/thresholds → 200; `M-01-error.jpg` |

## Each issue in detail
### 1. M-01 — Approval limits page fails to load
- **Steps:** 1. Sign in as State Manager. 2. Admin → Approval limits.
- **Seen:** …  **Expected:** …
- **Request:** `GET /api/v1/approvals/thresholds` → 200, x-request-id `…`; the screen rejected the answer.
- **Console:** …
- **Likely layer:** frontend schema (the answer arrived but couldn't be read) / backend (5xx) / permissions (403) / unclear.

## Blocked
- O-01…O-05: no Dispatch login.

## Test data created (to clean up)
- Leads: TEST Ramesh Patel 1 (POL/GJ/2026-27/00321), …
- Quotations, orders, dispatches, messages: …
```

Severity order: anything that blocks §S first, then ❌, then ⚠️; within each, the most-used screens first (Leads, Quotations, Orders).

---

## For an agent running this plan

- **Read §0 first**, especially the rules in §0.2. Keep credentials out of every file you write.
- **Drive the browser with Playwright.** Desktop 1440 × 900, then phone 360 × 780 with `hasTouch: true` and `colorScheme: "dark"`.
- **On every page,** collect `response` events with status ≥ 400, `console` errors and `pageerror`. Attach them to the case that was running.
- **Wait for content, not time.** Wait for the heading or the table; allow up to 30 s for the first load of each page. Something that never appears is ❌, with a screenshot.
- **Find elements by role and visible text,** e.g. `getByRole("button", { name: "New lead" })`. If a label differs slightly from this plan, use what the screen shows and note the difference as ⚠️ only if it would confuse a user.
- **Keep a running list of every record you create** for the report's clean-up section.
- **Order of work:** finish §A–§Q case by case, then run §S, then write both deliverables.
- **The issue report must stand alone.** Someone reading only the report should be able to reproduce every ❌.
