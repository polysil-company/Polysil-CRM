# Polysil CRM: what's ready, and how to demo it

What works today on the `integration` branch (everything up to pull request #47), in plain words. Read Part 1 for the list, Part 2 for what each feature does, and Part 3 to rehearse and run the demo, click by click.

> Everything here was built and tested against the backend's rules. Before showing a flow live, rehearse it once on the hosted app with the same logins. [Live-Test-Plan.md](Live-Test-Plan.md) is the full checklist if you want to test more widely.

---

## Part 1: what's ready, at a glance

**Signing in**

- Staff sign in with their work email and password.
- Dealers and distributors sign in with a one-time code sent to their mobile.
- People stay signed in across reloads. Signing out ends the session in every tab.

**Getting around**

- Each role sees only the menus it may use.
- Search for any page with **Ctrl + K**.
- Light and dark mode.
- Works on a phone.

**Dashboard**

- Open pipeline value, new leads, conversion rate, overdue follow-ups.
- Leads by stage and by source.
- The next follow-ups.

**Leads**

- One list of every enquiry, with search, filters and sorting.
- Add a new lead, with crops and land.
- Possible duplicates are flagged automatically.
- A full lead page with its complete history.
- Add notes.
- Move the lead through its stages. Each stage is explained in the app.
- Assign an owner and a channel partner.

**Quotations**

- Make a quotation from a lead, priced live as products are added (GST worked out).
- Discount approval when a discount is above the person's limit.
- Send it on WhatsApp, or share the link.
- The customer opens their own link and PDF, without any login.
- Record the customer's answer: accepted, negotiating or rejected.
- New versions (revisions).
- Full history.

**Approvals**

- One inbox for every manager, for discounts and orders.
- Approve or return with a reason.
- Cover for a manager on leave.
- Approval limits for orders, discounts and refunds, which an admin can change.

**Sales orders**

- Place an order from an accepted quotation.
- An approval chain by value (managers → Accounts → Dispatch).
- Return or cancel with a reason.
- Order PDF.
- Shipped-vs-open tracking.

**Dispatch**

- Record what left, item by item, with challan, invoice, transporter and vehicle.
- Void a dispatch.
- Close the rest of an order short.

**Notifications**

- A bell with an unread count.
- Each notification opens the lead, quotation or order it is about.
- Mark one or all as read.

**Messages**

- Staff chat one-to-one.
- Share a lead with a colleague in a message.

---

## Part 2: what each feature does

### Signing in and the app

Polysil staff sign in with their work email and password. Channel partners (dealers, distributors, sub-dealers) don't need a password: they enter their mobile number and type the code they receive. The app keeps people signed in and renews the session on its own. If someone signs out in one tab, every tab signs out.

The left menu shows only what a person's role allows:

- A field officer doesn't see **Approvals**.
- A dealer sees only their own channel's records.
- Items marked **Soon** are planned and not yet open.
- **Ctrl + K** (⌘ + K on a Mac) opens a search box for any page.
- The sun/moon button switches light and dark mode.
- On a phone, the menu is behind the **☰** button.

### Dashboard

The first screen after signing in. It shows, for the person's own area:

- **Open pipeline**: the value of all open leads.
- **New leads**: how many came in this period.
- **Conversion rate**: how many were won.
- **Overdue follow-ups.**

Each figure shows its change and a small trend. Below them: the pipeline by stage (count and value), where leads come from, and the next follow-ups, with overdue ones marked. A field officer sees their own work; a manager sees their whole district or state.

### Leads

**The list (Sales → Leads)**

- Every enquiry in one place, with a running total ("1–25 of 132").
- **Search** by farmer name, part of a mobile number, or the inquiry number (`POL/GJ/2026-27/00141`).
- **Filter** by stage, source (WhatsApp, website, QR code, agri fair…) and inquiry type.
- **Stage meanings.** The Stage filter explains each stage in one line, so a new person understands it.
- **Sorting.** Sort by customer name or value.
- **Shareable links.** Filters and the page stay in the web address, so a filtered list can be sent to a colleague.

**New lead**

- **What it asks for:** farmer name, mobile, place (district, taluka or village), inquiry type, irrigation system, crops (up to 10), land in acres, source, estimated value and a note.
- **Duplicates.** If the same farmer may already exist (same mobile, for example), the lead is still created and the duplicate is named, so nothing is lost.

**The lead page**

- **The lead itself:** stage, priority (hot, warm or cold), contact (with **Call** and **WhatsApp** buttons), place, owner and office, channel partner, crops, land, score and dates.
- **Its quotations,** every version.
- **Activity:** the full history as sentences, newest first. For example, "Asha Patel moved the lead from Contacted to Qualified", "assigned the lead to Ravi Joshi and made Khodiyar Irrigation the channel partner", or "QT/GJ/2026-27/00009 · v2 sent".
- **Notes.** Type in the box at the top of Activity, then press Ctrl + Enter.
- **Update stage** moves the lead along, and the menu explains each stage:
  - **New** → **Contacted** → **Qualified** are clicked by hand.
  - **Quoted** happens by itself when a quotation is sent.
  - **Negotiation** is recorded on the quotation.
  - **Won** comes when the customer accepts a quotation.
  - **Lost** needs a reason. A lost lead can be **reopened**.
  - **Merged** is a duplicate folded into another lead.
  - **Dormant** is set by the system after a long time with no activity.
- **Assign** (managers): change the owner, and choose the dealer or distributor handling the lead.

### Quotations

**Making one.** From a **Qualified** lead, click **New quotation**.

- Add items by typing a product name.
- As soon as you pause, the app prices the whole quotation: rate, discounts, taxable value, GST (split into CGST + SGST, or IGST across states) and total.
- A stand-in price is marked "Indicative rate".
- **Save draft** keeps it.

**Discount approval.** Each person has a discount limit.

- Within the limit, the quotation can be sent straight away.
- Above it, **Ask for approval** sends it, with a reason, to the lowest manager whose limit covers the discount.
- The draft shows "Waiting for approval", and the manager sees it in their Approvals inbox.
- Once approved, **Send** turns on. If it is returned, the manager's reason shows on the draft.

**Sending.** **Send** gives the quotation its number (`QT/GJ/…`) and a 45-day validity, and moves the lead to **Quoted**. It goes to the customer on WhatsApp, or without a message so the link can be shared by hand. The PDF is made in a few seconds.

**The customer's link.** The customer opens their link on their phone, with no login. They see who it's from, the total including GST, how many items, and until when it's valid. **View quotation** opens the PDF. The CRM records that they opened it.

**The customer's answer:** **Record answer** → *Accepted* (the lead is **Won**), *In negotiation* (the lead moves to Negotiation) or *Rejected*, with what the customer said.

**New versions.** **Revise** makes version 2 at today's prices. Sending it marks version 1 "Superseded", and the quotation keeps the same number.

**History and versions.** Every quotation shows its full story: drafted, sent, opened, the answer, revisions and each approval step.

### Approvals

**The inbox (Approvals in the menu)** is for managers, Accounts and Dispatch.

- **What's in it:** discount requests and orders waiting on you, oldest first. Each shows what it is, the party, the total, the discount asked, who raised it and how long it has waited.
- **The count.** The number beside Approvals in the menu always shows how many are waiting.
- **Approve or Reject.** A rejection needs a reason, which the person who asked reads.
- **Accounts** must always write a remark (the payment check).
- **Include steps below me** lets a senior manager cover for someone on leave.

**Approval limits (Admin → Approval limits).** Three ladders:

- **Order value:** District, State and Regional manager, including GST.
- **Discount on a quotation:** from the field officer's own limit up to Admin-Sales.
- **Refund on a complaint:** District, State and Regional manager, in rupees.

Everyone can read them. An admin changes one level at a time, and the app makes sure each level stays above the one below.

### Sales orders and dispatch

**Placing an order.** On an **accepted** quotation, **Place order** asks for the order type, delivery address, payment terms (Full payment or Credit) and remarks, then **Make draft order**. If the quotation already has an order, the button reads **Open order** instead.

**Approval chain.** **Submit for approval** gives the order its number (`SO/GJ/…`). It then goes, step by step:

1. through the managers by value (a small order stops at District; a big one goes up to Regional);
2. to **Accounts**, which confirms payment;
3. to **Dispatch**.

Each step appears in the next person's inbox. If anyone returns it, it comes back to the field officer with the reason, who can fix it and **Submit again**. Once approved, the order PDF is made and **Open PDF** appears.

**The order page:**

- the items, with ordered, sent, open and short quantities;
- totals with GST;
- the approval chain (who approved, when, and their remark);
- the dispatches;
- the party, delivery, payment terms and history.

**Dispatch (the Dispatch role):**

- **Record a dispatch:** what left, item by item, with time, challan, invoice, transporter and vehicle. The order becomes **Partly dispatched** or **Dispatched**.
- **Void** a dispatch with a reason. It stays on record, struck through.
- **Close short** with a reason, when the rest won't ship.

**The orders list (Sales → Sales orders)** shows each order's status, whom it waits on ("Waiting on Accounts"), how much has shipped, and filters including **Only my orders**.

### Notifications

The bell at the top right shows how many notifications are unread, for example:

- "Rohan Mehta assigned you a lead";
- "A discount for … needs your approval";
- "Sales order … was approved".

Clicking one opens that lead, quotation or order, and marks it read. **Mark all as read** clears them. The bell checks for new notifications every 30 seconds.

### Messages

**Messages** in the menu is one-to-one chat between staff. Choose a colleague and type; **Enter** sends. From any lead page, **Share with a colleague** sends that lead in a message, and the colleague clicks it to open the lead. Unread messages show a count in the menu. Partners don't have messages.

---

## Part 3: demo flows, click by click

### Before the demo (do this the day before)

1. **Logins.** You need at least a **Field Officer** (shown as "Employee" in the app) and a **District Manager**. For the full order story, also **Accounts** and **Dispatch**. An **Admin** login shows approval limits.
2. **Two people at once.** Use a normal window and a private (incognito) window side by side, signed in as two different people. That shows the hand-off live: the officer asks, the manager approves.
3. **A safe mobile number.** Use your own phone number for the demo lead. Then "Send on WhatsApp" and the customer's link arrive on a phone you hold, which makes a great live moment.
4. **Rehearse once,** end to end, with the same logins. Note any lead or quotation numbers you want to come back to.
5. **Clear names.** Name demo records clearly, e.g. farmer "Demo — Ramesh Patel", so they're easy to tidy up later.

### Suggested demo order (about 20 minutes)

1. Sign in and look around (Flow 1): 2 min.
2. A new enquiry becomes a qualified lead (Flows 2–4): 4 min.
3. A quotation with a discount that needs approval (Flows 5–6): 5 min.
4. Send it; the customer opens it on a phone (Flows 7–8): 3 min.
5. The customer accepts; place the order; approvals; dispatch (Flows 9–11): 5 min.
6. Notifications and messages (Flows 12–13): 1 min.

---

### Flow 1: sign in and look around

**Who:** any staff login.

1. Open the app → choose **Staff email** → type the work email and password → **Sign in**.
2. You land on the **Dashboard**. Point out the four figures, the pipeline by stage, sources and follow-ups.
3. Show the left menu: **Overview**, **Sales**, **Service**, **Admin**. Items marked **Soon** are coming next.
4. Press **Ctrl + K**, type `lead`, press **Enter**: it jumps to Leads.
5. Click the sun/moon at the top right to switch to dark mode, and back.

*Say:* "Each person sees only what their role allows. A field officer has no Approvals; a manager sees their whole area."

### Flow 2: capture a new enquiry (a new lead)

**Who:** Field Officer.

1. **Sales → Leads** → **New lead** (top right).
2. Fill in:
   - **Farmer name:** `Demo — Ramesh Patel`
   - **Mobile number:** your demo phone number
   - **Territory:** type a taluka name (e.g. `Gondal`) and pick it. Districts and villages work too.
   - **Inquiry type**, **Irrigation system**
   - **Crops:** pick two, e.g. Cotton and Groundnut
   - **Land:** `4.5`
3. **Create lead**. A message confirms it, and the lead is at the top of the list.

*Show also:* type the same mobile again in a second New lead → it is still created, and the app names the possible duplicate.

### Flow 3: find leads quickly

**Who:** any.

1. On **Leads**, type part of a name or mobile in the search box.
2. Open **Stage**. Every stage has a one-line explanation. Tick **Qualified** and **Negotiation**.
3. Click the **Customer** column header to sort A→Z, and **Value** to sort by value.
4. Copy the web address and open it in a new tab: the same filtered list opens.

### Flow 4: work the lead (notes, stage, assign)

**Who:** Field Officer, then a District Manager for assigning.

1. Open **Demo — Ramesh Patel** from the list.
2. Point out the details card: crops as tags, land in acres, **Call** and **WhatsApp** buttons.
3. In **Activity**, type a note: `Called; interested in drip for 4.5 acres of cotton` → **Ctrl + Enter**. It appears at the top.
4. **Update stage**. The menu explains the current stage and each move. Choose **Mark as contacted**.
5. **Update stage** → **Mark as qualified**. (Point out "Quoted" is greyed: "Happens when a quotation is sent".)
6. Scroll to **Activity**: each step is a sentence with who and when.
7. *(As District Manager)* **Assign** → choose an **Owner** and a **Channel partner** (type a dealer's name) → **Save**. The history says who it was assigned to.

*Optional, losing and reopening:* **Update stage** → **Mark as lost…** → it asks for a reason → choose one → confirm. Then **Update stage** → **Reopen lead…**: it's back at the stage it was lost from.

### Flow 5: make a quotation

**Who:** Field Officer, on the **Qualified** lead.

1. On the lead page, in **Quotations**, click **New quotation**.
2. Under **Items**, type a product name (e.g. `drip`), pick it, and enter a quantity. **Add item** to add another.
3. Pause: the app prices it. Point out the rate, taxable value, GST split and total on each line and in **Totals**.
4. Give one item a discount in its discount box, above your limit (e.g. `20`).
5. **Save draft**. The quotation opens as a **Draft**.

*Say:* "The backend prices it, not the screen, so the figures always match the price list and tax rules."

### Flow 6: discount approval (two windows)

**Who:** Field Officer (window 1) and District Manager (window 2).

1. *(Officer)* The draft shows that the discount needs approval, with your limit. Click **Ask for approval** → type a reason (`Repeat customer; matching a competitor`) → confirm. It now reads **Waiting for approval**.
2. *(Manager)* The bell shows a new notification: "A discount for Demo — Ramesh Patel needs your approval". The **Approvals** count in the menu went up.
3. *(Manager)* **Approvals** → the request is listed with the discount asked and who raised it → **Approve** → confirm.
4. *(Officer)* The draft now says the discount is approved, and **Send** is on.

*Show also:* on another draft, the manager presses **Reject** without a reason → the app asks for one ("Say why. The person who asked reads it.") → with a reason, the officer sees it on their draft.

### Flow 7: send the quotation

**Who:** Field Officer.

1. On the approved draft, click **Send**.
2. Choose **Send on WhatsApp** (only to your own demo number), or send without a message to share the link yourself.
3. **Send the quotation**. It now has a number (`QT/GJ/2026-27/…`), is valid for 45 days, and the lead has moved to **Quoted**.
4. "Preparing PDF…" turns into **Open PDF** in a few seconds. Open it: the formatted quotation.

### Flow 8: the customer's view, on a phone

**Who:** nobody signed in, on your phone.

1. Open the WhatsApp message, or the link copied from the quotation page (**Copy** next to the customer link).
2. The page shows who it's from, the total including GST, the number of items, and the validity.
3. Tap **View quotation**: the PDF opens.
4. Back in the CRM, the quotation's history now says it was **opened by the customer**.

### Flow 9: the customer accepts, then a new version

**Who:** Field Officer.

1. *(Optional, negotiation)* On the sent quotation: **Record answer** → **Mark as in negotiation…** → type what the customer said → confirm. The lead moves to **Negotiation**.
2. *(Optional, new version)* **Revise**: version 2 opens as a draft at today's prices. Change a quantity → **Save draft** → **Send**. Version 1 now reads "Superseded by v2", with the same number.
3. **Record answer** → **Mark as accepted…** → confirm. The quotation is **Accepted**, and the lead is **Won**.

### Flow 10: place the order and take it through approvals

**Who:** Field Officer, then each approver.

1. On the accepted quotation, click **Place order**.
2. Choose the order type, check the **Deliver to** address, choose payment terms (**Full payment** or **Credit**), add a remark → **Make draft order**. The draft order opens with the quotation's items and totals.
3. **Submit for approval**. It gets its number (`SO/GJ/…`), and the page shows the **approval chain**: managers by value, then Accounts, then Dispatch.
4. *(District Manager)* **Approvals** → the order → **Approve**.
5. *(Accounts)* **Approvals** → the order → **Approve**. A remark is required (e.g. `Advance received`).
6. *(Dispatch)* **Approvals** → the order → **Approve**.
7. *(Officer)* The order is **Approved**. The bell says so, and **Open PDF** shows the order PDF. The chain lists who approved each step and when.

*Show also:* if a manager rejects with a reason, the order returns to the officer as a draft, showing the reason. The officer edits it and clicks **Submit again**.

### Flow 11: dispatch

**Who:** Dispatch.

1. Open the approved order → **Record a dispatch**.
2. Enter what left for each item (part of it, to show a partial dispatch), **Left on**, **Challan number**, **Invoice number**, **Transporter**, **Vehicle number** → save.
3. The order is now **Partly dispatched**. The items show sent and still open, and the dispatch is listed.
4. *(Optional)* **Void** the dispatch with a reason: it stays listed, struck through, and the items are open again.
5. *(Optional)* **More actions** → **Close short** with a reason, when the rest won't ship.
6. **Sales → Sales orders** shows each order's status, whom it waits on, and a bar for how much has shipped.

### Flow 12: notifications

**Who:** any.

1. Click the bell at the top right: the latest notifications, unread ones marked.
2. Click one: it opens that lead, quotation or order, and the count drops.
3. **Mark all as read**.

### Flow 13: messages and sharing a lead

**Who:** two staff (two windows).

1. *(Window 1)* **Messages** → **New message** → search a colleague → choose them → type `Can you visit this farmer on Friday?` → **Enter**.
2. On a lead page, click **Share with a colleague** → choose the colleague → send. The message carries the lead.
3. *(Window 2)* **Messages** shows an unread count. Open the conversation → click the lead in the message to open it.

### Flow 14 (admin only): approval limits

**Who:** Admin (read-only for others).

1. **Admin → Approval limits**. Three ladders: **Order value**, **Discount on a quotation**, **Refund on a complaint**.
2. Point out how it works: each manager approves up to their limit, and anything bigger goes to the next level.
3. *(Only if agreed beforehand)* Change a level, then put it back. The app refuses a limit that isn't above the level below.

---

## Part 4: not built yet (good answers for the client's questions)

These are planned. The backend already supports most of them, and the app shows them as **Soon** in the menu.

- **Tasks and follow-ups:** daily calls and visits, the planner, meeting minutes. A lead's follow-up date comes with this.
- **Complaints:** registering a complaint, the quality check, refunds and replacements. (The refund approval limits already show.)
- **Subsidy applications.**
- **Direct orders:** an order typed in item by item without a quotation, and one combined order for a dealer.
- **Editing or deleting a lead,** the duplicates queue, and merging duplicates.
- **Lead QR codes and the public enquiry form.**
- **Channel partners, schemes, marketing and reports** screens.
- **Admin masters:** products, price lists, tax rates, users and roles, offices, territories.
