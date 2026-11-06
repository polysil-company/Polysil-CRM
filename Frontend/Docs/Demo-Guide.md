# Polysil CRM: what's ready, and how to demo it

What works today on the `integration` branch (everything up to pull request #84), in plain words. Read Part 1 for the list, Part 2 for what each feature does, and Part 3 to rehearse and run the demo, click by click.

- **Demo 1** (2 October) showed Flows 1–14.
- **Demo 2** adds Flows 15–22: lead capture with QR codes, tidying leads, tasks and meetings, direct orders, the dispatch queue and complaints. Part 3 opens with a suggested order for it.
- **Subsidy** (Flows 23–26) is built and waiting for review (PRs #77, #78, #79, #86). Show it only once those are merged.

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
- Filter by area: districts, then a district's talukas, with counts. *(new)*
- Edit a lead; an admin can delete one. *(new)*
- Possible duplicates: compare a pair side by side, merge or dismiss. *(new)*
- QR codes for fairs, dealers and print, and a public enquiry page confirmed by a WhatsApp code. *(new)*
- Download the list as Excel. *(new)*

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
- A direct order typed in item by item, without a quotation. *(new)*
- Download the list as Excel. *(new)*
- An approval chain by value (managers → Accounts → Dispatch).
- Return or cancel with a reason.
- Order PDF.
- Shipped-vs-open tracking.

**Dispatch**

- Record what left, item by item, with challan, invoice, transporter and vehicle.
- Void a dispatch.
- Close the rest of an order short.
- The Dispatch queue: orders waiting to ship, and a log of what left. *(new)*

**Tasks and meetings** *(new)*

- My day: overdue first, then today's calls, visits and meetings.
- Team: each person's due, done and overdue for a manager.
- Tasks and meeting minutes on a lead, with action items that become tasks.
- Edit, reassign, mark done, cancel, reopen.
- All tasks, with filters and an Excel download.

**Complaints** *(new)*

- Raise a complaint (from a lead, an order or on its own) with products and photos.
- The manager's check, then the QC verdict.
- The remedy: a refund through the Approvals inbox (Accounts records the UTR), a replacement order, or no action.
- Response and resolution targets, with a "Late" mark; set by an admin.
- "Waiting on me" queues and an Excel download.

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

### Lead capture and keeping leads tidy *(new)*

**QR codes (Sales → QR codes).** A QR code per fair, dealer, poster or van. Each one shows:

- its name and code;
- how many leads it brought;
- its campaign, dealer and area.

**Download to print** saves a sharp image. **Copy link** gives the web address. The code never changes, so printed copies keep working even after the code is renamed, re-pointed or switched off.

**The enquiry page (`/enquiry`, no login).** A farmer scans the code on their phone and fills in:

- name, mobile, area (already set when the code names one), village, the system they want, how they'll buy, and a note.

They confirm their mobile with a six-digit code sent on WhatsApp and get an inquiry number to keep. The lead lands in the CRM with its source, dealer and area.

**Area filter.** The **Area** pill on Leads lists the districts that hold leads, each with its count. Open a district to pick its talukas.

**Edit, delete, duplicates.**

- **Edit** (beside Assign) changes any of the lead's own details; the history says what changed.
- An admin can **Delete** a lead.
- **Possible duplicates** (on the Leads toolbar) shows each suspect pair side by side, with what matched. **Keep** one merges the other into it, moving its history across. **Not a duplicate** clears the pair.

### Tasks and meetings *(new)*

**Service → Tasks** has three views.

- **My day:** what's overdue on top, then today by time: calls, visits, meetings and follow-ups, each with its lead.
  - **Done** asks what happened.
  - **Cancel task** asks why.
  - A done task can be **Reopened**.
- **Team** (managers): one row per person with due, done and overdue. Click a row to see that person's day and give them a task.
- **All tasks:** filters for status, kind, person and overdue, and **Download Excel**.

**On a lead's page:**

- its tasks and meetings;
- **Record minutes:** who was there, what was discussed, and action items. Each action item becomes a task for whoever it names.

### Direct orders and the dispatch queue *(new)*

**New order** (on a qualified lead, or on Sales orders) types an order in item by item, priced live like a quotation. It then goes through the same approval chain.

**Operations → Dispatch queue** has two lists:

- **To ship:** every approved order still waiting to leave, with how much has gone. **Record a dispatch** opens the order with the form ready.
- **Dispatched:** the log by day, including voided dispatches with their reason.

### Complaints *(new)*

1. **Raise.** A field officer or dealer clicks **New complaint**, or **Raise a complaint** on a lead or order. They give the type, severity, what went wrong, the contact, the challan and supply date, the defective products, and photos.
2. **Submit.** The complaint gets its number (`Poly/Comp./2026-27/GJ/NN`) and its targets start.
3. **Check (manager).** **Approve, send to QC** (optionally a new severity and an owner), or **Return to fix** with a remark the raiser reads.
4. **QC verdict.** Defect or no defect, what QC found, and the sample's dates. No defect closes it.
5. **Remedy (QC).**
   - **Refund:** goes to the managers by amount, then Accounts, in the Approvals inbox. Accounts enters the UTR, which closes the complaint.
   - **Replacement:** a replacement order.
   - **No action.**

"Late" marks a missed target. **Admin → Complaint targets** sets the first-response and resolution times per severity, in working hours or round the clock.

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

### Suggested order for Demo 2 (about 25 minutes)

Start with a one-minute recap: the dashboard, then a lead with its quotation and order from Demo 1. Then show what's new:

1. A farmer at a fair becomes a lead from a QR code (Flow 15): 4 min.
2. Find and tidy leads: area filter, edit, duplicates (Flow 16): 3 min.
3. The field officer's day and the manager's team view (Flows 17–18): 5 min.
4. A direct order, then the dispatch queue (Flows 19–20): 4 min.
5. A complaint from the farmer to QC (Flow 21): 5 min.
6. The refund through approvals to Accounts (Flow 22): 3 min.

**Logins for Demo 2:** Field Officer (Employee), District Manager, QA, Accounts, Dispatch and Admin. Keep two windows: officer and manager.

**Extra preparation for Demo 2:**

- Print one QR code, or keep it on a second screen, and have a phone ready to scan it.
- Use your own mobile for the enquiry: the WhatsApp code goes to it.
- Have one approved order with items still to ship, so the Dispatch queue isn't empty.
- Have a small photo on the laptop to attach to the complaint.

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

## Part 3b: Demo 2 flows, click by click

### Flow 15: a farmer at a fair becomes a lead (QR code)

**Who:** Field Officer (or a manager), then a farmer with no login on a phone.

1. **Sales → QR codes** → **New QR code**.
2. Name it `Demo — Rajkot Agri Fair`. Optionally choose a campaign, a **dealer** and an **area** (e.g. Rajkot) → save.
3. The code appears with its QR. Click **Download to print** (it saves a PNG), or **Copy link**.
4. *(Phone)* Scan the QR. The **enquiry page** opens, saying "Enquiry through <dealer>" when a dealer was chosen, with the area already set.
5. Fill in the name (`Demo — Kiran Patel`), **your own mobile**, village, system and a note.
6. Tap **Send me a code on WhatsApp**, then type the six digits from WhatsApp → **Send my enquiry**.
7. The page shows the **inquiry number** to keep.
8. *(Laptop)* **Sales → Leads**: the new lead is at the top, with its source, dealer and area. Back on **QR codes**, the code's lead count went up by one.

*Say:* "Every scan is a lead, tagged with where it came from. Nobody types it in, and the mobile is confirmed."

*Show also:* a switched-off code still opens the plain form, so printed posters never break.

### Flow 16: find and tidy leads

**Who:** District Manager (and Admin for delete).

1. **Sales → Leads** → the **Area** pill. The districts are listed with their lead counts. Open **Rajkot** and tick two talukas: the list narrows, and the pill names the area.
2. Open a lead → **Edit** (beside Assign). Change the land or a crop → save. **Activity** says which fields changed.
3. Back on **Leads** → **Possible duplicates**. Each pair is side by side, with what matched (e.g. the same mobile).
4. On one pair, click **Keep POL/GJ/…** under the better lead → confirm. The other is merged into it, with its history.
5. On another pair, click **Not a duplicate**: the pair is cleared.
6. **Download Excel**: the leads the filters show, as a spreadsheet.
7. *(Admin, optional)* On a demo lead, **Delete** → confirm. It goes back to the list.

### Flow 17: the field officer's day

**Who:** Field Officer.

1. **Service → Tasks** → **My day**. Overdue tasks are on top, then today's by time.
2. **New task** → *Visit* `Survey the field for drip`, today at 15:00, for yourself, on the lead `Demo — Kiran Patel` → **Add task**.
3. On a task's menu → **Done** → write what happened (`Farmer agreed; quotation next week`) → save. It moves to done.
4. On another task → **Cancel task** → give a reason.
5. Open the lead `Demo — Kiran Patel`: the **Tasks** card lists the visit.
6. On the lead, **Record minutes**: who was there (one per line), what was discussed, and an action item (`Send quotation`, due Friday, for yourself) → save. The action item appears as a task, marked "From meeting minutes".

### Flow 18: the manager's team view

**Who:** District Manager.

1. **Service → Tasks** → **Team**. Each person's due, done and overdue for today.
2. Click a person: their day opens. **New task** there gives them a task. **Back to team** returns.
3. On one of their open tasks → **Edit or reassign** → choose another person → save. "Given to …" confirms it.
4. **All tasks** → tick **Overdue only** → **Download Excel**.

### Flow 19: a direct order without a quotation

**Who:** Field Officer.

1. **Sales → Sales orders** → **New order** (or **New order** on a qualified lead's page).
2. If typing afresh, choose the **place of supply** first. From a lead, the party and place come from the lead.
3. Add items by typing a product name, with quantities. They are priced live, with GST.
4. Choose the order type, delivery address and payment → save. The draft order opens.
5. *(Optional)* **Edit items** to change a quantity.
6. **Submit for approval**. The order follows the same chain as Flow 10.

### Flow 20: the dispatch queue

**Who:** Dispatch.

1. **Operations → Dispatch queue** → **To ship**. Each approved order still waiting to leave, partly sent ones with how much has gone (e.g. "46% sent").
2. **Record a dispatch** on one. The order opens with the form ready. Enter the quantities, challan, invoice, transporter and vehicle → save.
3. **Dispatched**: the log for today, newest first. The new dispatch is there with its order and challan.

### Flow 21: a complaint, from the farmer to QC

**Who:** Field Officer (or a dealer), then District Manager, then QA.

1. *(Officer)* Open the order (or lead) the complaint is about → **Raise a complaint**. Or use **Service → Complaints** → **New complaint**.
2. Fill in:
   - **Type** and **severity**;
   - what went wrong;
   - the contact and mobile;
   - the challan and supply date;
   - the defective products (`2` of `10` supplied).

   Save the draft.
3. **Add files** → choose *Photo* → pick the photo. It shows as a thumbnail.
4. **Submit**. It gets its number (`Poly/Comp./2026-27/GJ/…`), and its targets start.
5. *(Manager)* **Service → Complaints** → **Waiting on me** → open it → **Check** → **Approve, send to QC**. Optionally raise the severity and set an owner → save.
   - *Show also:* **Return to fix** with a remark. The officer sees it on the draft, fixes it and clicks **Submit again**.
6. *(QA)* **Waiting on me** → open it → **Give the QC verdict** → *Approved* (a defect), what QC found, and the sample's received and tested dates → save.

### Flow 22: the refund, through approvals to Accounts

**Who:** QA, then District Manager, then Accounts.

1. *(QA)* On the QC-approved complaint → **Choose the remedy** → *Refund*: amount `1500`, who is paid, why → save. The Remedy card shows its approval steps.
2. *(Manager)* **Approvals**: a "Complaint refund" row with the amount and payee → **Approve**.
3. *(Accounts)* **Approvals** → the refund → **Approve** → enter the **payment reference** (UTR) → confirm.
4. Back on the complaint: **Closed**, with the UTR and every step in its history.
5. *(Admin)* **Admin → Complaint targets**: the first-response and resolution targets per severity. Point out the "Late" mark on the complaints list when one is missed.
6. **Service → Complaints** → **Download Excel**.

*Say:* "The same approval chain as orders, the same inbox. Accounts can't approve a refund without the UTR."

---

## Part 3c: subsidy (after PRs #77, #78, #79 and #86 are merged)

Rehearse these on the hosted app once the four pull requests are on `integration`.

### Flow 23: the subsidy calculator

**Who:** Field Officer.

1. **Sales → Subsidy** → **Calculator** → **Drip**.
2. Pick a crop, then type the **area** and **lateral spacing**. Add a field-unit item or two and the head unit.
3. Pause: the figures appear. Point out the unit cost, the eight farmer categories with the subsidy and the farmer's share, and the summary per block.
4. Switch to **Sprinkler**: choose the area from the scheme's steps. The derived items and the DBT farmer payable appear.

### Flow 24: a subsidy application from a lead

**Who:** Field Officer, then the subsidy desk.

1. On a qualified, subsidised lead → **Start subsidy application**. The calculator opens with the lead's scheme (from its state).
2. Enter the design, then choose the farmer's **category** → **Start application**.
3. The application opens with its stored figures. **Record stage** → choose the stage, the date and its fields (e.g. App. Inward Date) → save.
4. **Documents**: **Add** a file against a checklist item.
5. *(GGRC only)* Download the **PIMS sheet**.
6. **Subsidy → Applications**: the worklist with status, stage, search and Excel.

### Flow 25: subsidy reports

**Who:** State Manager.

**Subsidy → Reports** has three tabs:

- **Stages:** money and count by stage.
- **Supply:** supplied and not supplied by district.
- **Ageing:** the six ageing figures per application.

Each has **Download Excel**.

### Flow 26: masters, and a new state's scheme

**Who:** Admin.

1. **Admin → Subsidy masters**. The **Overview** shows GGRC as Ready on all three systems, with its stages.
2. **New scheme** → code `UPMIS`, name, state **Uttar Pradesh**, start from GGRC, systems Drip and Sprinkler → **Set up the scheme**.
3. The overview says **Not ready** and lists what each system lacks. Click **Open** beside "The regular unit-cost matrix": it goes to **Unit costs**.
4. On **Crop spacings** → **Add rows from a date** → add one crop → **Save the revision**.

*Say:* "Rates change from a date; applications already started keep their figures. A new state is set up here, without a developer."

---

## Part 4: not built yet (good answers for the client's questions)

These are planned. The backend already supports most of them, and the app shows them as **Soon** in the menu.

- **Accounts queue:** the backend finished it; the screen is next. Meanwhile, Accounts works from the Approvals inbox.
- **Admin masters:** products, price lists, tax rates, users and roles, offices, territories, partners, and lookups such as complaint types.
- **Channel partners, schemes, rewards and dealer commission, marketing material and reports** screens.
- **The dealer's own portal** views.
- **Campaigns, the customer record, and export and sample orders:** the backend has them; the screens come later.
- **One combined order** from several quotations of one dealer.
