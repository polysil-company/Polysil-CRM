# Polysil CRM: what works today

Tested on the test site (polysil-test.pranayx.tech) on 22–23 October 2026, with each staff role, on a computer and on a phone, in light and dark mode. Everything marked TEST was created for this check.

## Signing in

**What it's for:** each person signs in to see only the work and the area that are theirs.

**Works**
- Staff sign in with their work email and password and land on their dashboard.
- A wrong password gives a clear message. The email stays filled in, and the password field clears.
- A warning shows when Caps Lock is on.
- A link to a page opens that page after signing in, not the dashboard.
- Refreshing the page keeps you signed in. Signing out in one tab signs you out in every tab.

**Not tested**
- Dealers signing in with a one-time WhatsApp code. No dealer code was available for this check.

**How to try it**
1. Open the site and choose **Staff email**.
2. Enter your work email and password and press **Sign in**.

## Getting around

**What it's for:** reach any screen in a click or two, on a computer or a phone.

**Works**
- Each role sees its own menu. A field officer has no Approvals; Accounts and Dispatch see their own queues.
- **Ctrl + K** opens a search over pages, actions and records.
- **Ctrl + B** folds the side menu down to icons.
- The sun/moon button switches between light and dark. Both stay easy to read.
- On a phone the menu sits behind the ☰ button, and every page fits the screen.

**Works, with a problem**
- In the Ctrl + K search, after you type a word, nothing is highlighted, so pressing Enter does nothing. Press the down arrow first, then Enter.
- The browser tab shows no Polysil icon.

**How to try it**
1. Press **Ctrl + K**, type "lead", press the down arrow twice, then press Enter.

## Dashboard

**What it's for:** the day's position at a glance.

**Works**
- Four figures: open pipeline (₹), new leads with the change and a small trend, conversion rate, and overdue follow-ups.
- Leads by stage with counts and value, and area by irrigation system. Orders against target by month.
- A manager sees a wider area than an officer: Rajkot's district manager sees 47 leads, Gujarat's state manager 95.

**Works, with a problem**
- "Overdue follow-ups" showed 0 for an officer whose task list had one overdue follow-up.

## Leads: the list

**What it's for:** every enquiry, from WhatsApp, the website, QR codes or a field visit, in one list, so nobody is missed.

**Works**
- 25 leads per page, with a total that matches the menu.
- Search by part of a name, part of a mobile number, or an exact inquiry number.
- Filter by stage (each stage explained in one line), source, area, type and campaign.
- Sort by customer or value.
- Filters and pages stay in the web address, so a refresh or a copied link opens the same view.
- When nothing matches, the page says so, with **Clear filters**.
- **Download Excel** works.

**Works, with a problem**
- On a laptop-sized screen the last columns (follow-up, value) are cut off at the right edge until you scroll the table.

**How to try it**
1. **Sales** → **Leads**.
2. Type part of a farmer's name in the search box, or choose **Stage** → **Qualified**.

## Leads: capturing an enquiry

**What it's for:** take an enquiry in under a minute, in the field or at the office.

**Works**
- Name, mobile, place, inquiry type, irrigation system, crops (up to 10) and land in hectares (acres shown alongside).
- The place search offers districts, talukas and villages, but never the whole state.
- Each missing field says what's needed, on the field itself.
- The farmer gets a WhatsApp acknowledgement.
- If the same mobile is already on another lead, the app says so and flags both leads for review.

**Works, with a problem**
- The farmer-name box turns red as soon as you move to another field, before you've typed anything.

**How to try it**
1. **Leads** → **New lead**.
2. Fill in the name and mobile, pick the place, type and system.
3. Press **Create lead**. The lead appears at the top of the list with its inquiry number.

## Leads: working a lead (notes, stages, assigning)

**What it's for:** everyone sees what happened with a farmer and what's next.

**Works**
- **The lead's page:** contact, place, owner, crops, land, score and a "Hot / Warm / Cold" badge. Call and WhatsApp buttons. A warning when the farmer may be a duplicate.
- **Notes** are saved with Ctrl + Enter and appear at once.
- **Update stage** explains each move: New → Contacted → Qualified.
  - "Quoted" happens by itself when a quotation is sent.
  - **Mark as lost** asks for the reason.
  - **Reopen** puts the lead back where it was.
- **Assigning:** a district manager can change the owner and the dealer. An officer can change only the dealer, and the app says why.
- **Activity** lists every change with who and when, with **Show older activity** for long histories.
- The lead's page also holds its tasks, meeting minutes, documents and the subsidy application.

**Works, with a problem**
- Attaching a document to a lead also offers dealer documents (GST certificate, PAN card, shop photo).

## Quotations: making one

**What it's for:** a correct, priced quotation from the price list, with GST worked out.

**Works**
- A quotation can be made only once the lead is qualified, and the app says so.
- Pick products by typing part of the name. Each line shows the rate, taxable value, GST and total as you type. Up to three discounts per line.
- **GST:**
  - Each item's GST rate starts from its tax code. It can be changed, and the change is marked "Changed from 5%".
  - Same-state quotations show CGST and SGST.
- **Freight** can be added, and is taxed at the highest rate among the items.
- **Farmer (subsidised) quotations** have no GST choice and no freight, as intended.
- Rates that are still stand-ins are marked "Indicative" on screen and on the PDF.
- The saved draft shows exactly the totals the form showed.

**Doesn't work yet**
- A quotation can be saved with an empty item line. It then becomes an empty draft with a total of ₹0.

**Works, with a problem**
- Changing only the terms on a draft also records "Items changed" in its history.
- While building, freight isn't shown on its own line in the summary. It appears on the saved quotation.

**How to try it**
1. Open a qualified lead → **New quotation**.
2. Type a product name, pick it, enter a quantity, and add a 3% discount.
3. Press **Save draft**.

## Quotations: discount approval

**What it's for:** larger discounts need a manager's yes before the farmer sees them.

**Works**
- **The officer's limit:** a field officer can give up to 5%. Above that the quotation can't be sent; it says whose approval it needs and offers **Ask for approval** with an optional reason.
- **Who approves:**
  - 8% and 10% went to the district manager.
  - 25% went to Admin-Sales, the level that covers it.
- **After the decision:**
  - Once approved, the officer sees "Discount approved" and can send.
  - If refused, the officer sees the manager's reason, which is always required, and can change the discount.

**Works, with a problem**
- The waiting message reads "Waiting for a Admin sales" (wording).

## Quotations: sending and the customer's link

**What it's for:** the farmer gets a proper quotation on their phone.

**Works**
- **Sending:**
  - **Send** gives the quotation its number (QT/GJ/…) and 45 days' validity, and moves the lead to Quoted.
  - You can send it on WhatsApp or copy the link and share it yourself.
- **The PDF** is ready within about 10 seconds and opens in a new tab.
- **The customer's link** opens without signing in. It shows the number, the total with GST, the item count and the dates, with no phone numbers or addresses. A mistyped link says it doesn't open a quotation.

**How to try it**
1. On a draft press **Send** → **Don't send a message** → **Send quotation**.
2. Copy the customer link and open it in a private window.

## Quotations: the customer's answer and new versions

**What it's for:** record what the farmer said and keep every version.

**Works**
- **Recording the answer:**
  - **Record answer** → In negotiation, Accepted or Rejected, with a note.
  - "In negotiation" moves the lead to Negotiation.
  - "Accepted" makes the lead **Won** and offers **Place order**.
- **New versions:**
  - **Revise** makes version 2 at today's prices.
  - Sending it marks version 1 "replaced", and the number stays the same.
  - The lead's page lists every version.
- An administrator can delete a draft. A sent quotation can't be deleted.

## Approvals

**What it's for:** one inbox for everything waiting on you.

**Works**
- Discounts and orders side by side, oldest first. Each shows who raised it, how long it has waited, the total, the discount, and "GST changed on 1 line" when a rate was changed.
- The menu count matches the inbox.
- **Rejecting** needs a reason.
- **Accounts** must note the payment check before approving.
- A manager can **Include steps below me**, to cover for someone on leave.
- Field officers have no Approvals.

**Works, with a problem**
- Two older orders seem stuck: one waits for a district manager that doesn't exist, one for a regional manager.

## Approval limits

**What it's for:** who may approve how much.

**Works**
- **Admin sees three ladders:**
  - order value: district ₹1 lakh, state ₹5 lakh, regional no limit;
  - quotation discount: officer 5%, district 10%, state 15%, regional 20%, Admin-Sales no limit;
  - complaint refunds.
- **Changing a limit:** a limit below the level under it is refused, with the reason. A valid change applies at once. The limit changed in this test was put back.

**Doesn't work yet**
- The state manager can't open the page ("You don't have access"), although it should be readable for them.

## Sales orders

**What it's for:** from an accepted quotation to an approved order, with every approval recorded.

**Works**
- **Place order** copies the quotation's items, prices, GST and freight into a draft order. Delivery address, payment terms and remarks can be changed.
- **Submit** gives it its number (SO/GJ/…) and lists who approves: the managers by value, then Accounts, then Dispatch.
- Each approver sees it in turn. At the end the order is **Approved**, with a PDF and the full history.
- **If a manager returns an order,** it comes back as a draft with their reason, and **Submit again** works.
- An order can be cancelled with a reason.
- The list filters by status, type, area and office, and "Only my orders". It shows how much has been sent.
- An order can also be typed in directly from a lead with **New order**.

**Works, with a problem**
- Order lines read "Warehouse short: -500 MTR available" when the warehouse has no stock. The wording is confusing, and stock goes below zero.

## Dispatch

**What it's for:** record what left the warehouse, against which order.

**Works**
- **Record dispatch:**
  - per item, with challan, invoice, transporter and vehicle;
  - more than is still open is refused;
  - the order shows "Partly dispatched", then "Dispatched".
- **Fixing mistakes:**
  - A dispatch can be voided with a reason. It stays listed, struck through, and the quantities are open again.
  - The rest of an order can be closed short with a reason.
- Managers can read the order but have no dispatch buttons.

## Notifications

**What it's for:** know at once when something needs you or has happened.

**Works**
- The bell shows how many are unread: "A discount of 8% … waits for your approval", "Order … was approved".
- Clicking one opens the record and marks it read. **Mark all as read** clears the count.

## Messages

**What it's for:** talk to a colleague about a lead without leaving the CRM.

**Works**
- **New message** → pick a colleague → write. Their unread count shows in the menu and clears when they open it.
- **Share with a colleague** on a lead sends a link to the lead; the colleague opens it in one click.

## Tasks and the day planner

**What it's for:** every call, visit and follow-up, planned and checked off.

**Works**
- **My day:** overdue tasks first, then today's.
  - Move day by day or pick a date.
  - **New task:** a task with no time is due at 6 pm.
- **Finishing a task:** **Mark done** asks what happened. A task can be reopened or cancelled with a reason.
- **On a lead:**
  - Tasks can be added from the lead's page.
  - **Record minutes** of a meeting turns each agreed action into a task.
- **For managers:**
  - A **Team** view: each person's due, done and overdue tasks.
  - An **All tasks** list with filters and Excel download.

## QR codes and the enquiry page

**What it's for:** a farmer scans a code at a stall or a dealer's counter and becomes a lead.

**Works**
- **Making a code:** managers make a code (optionally for a dealer, a campaign or an area), download it as an image to print, and copy its link.
- **Changing a code:** renaming it or switching it off and on keeps the same code and link.
- **The enquiry form** opens without signing in: name, mobile, place, system and how they'll buy. With an area code, the farmer skips choosing the area.

**Not tested**
- Sending the farmer's WhatsApp check code. No code was sent in this test.

## Products and prices

**What it's for:** one catalogue, price lists and GST rates that every quotation uses.

**Works**
- **The catalogue:** 1,092 products, with search, status and section filters. Each product shows its unit, tax code and GST rate, and "stand-in" where a figure isn't confirmed.
- **The other tabs:**
  - the GST rates in force;
  - the price lists with their dates and rates;
  - our GST registrations.
- Read-only for field officers.

**Doesn't work yet**
- Adding a product: the Category and Unit lists are empty, so a new product can't be saved. The server is missing an update that is already built.
- The Category filter on the catalogue is empty for the same reason.

## Users and roles

**What it's for:** add people, give them a role and an area, and take access away.

**Works**
- **The list:** everyone, with their role, office, last sign-in and open leads. Search and filter by role and status.
- **New person:** the form names each missing field. The temporary password is shown once, to give in person.
- **Changing a person:** edit them, deactivate them, set a new temporary password, sign them out everywhere, or hand over their leads.
- You can't deactivate or delete yourself.
- Field officers can't open this page.

**Works, with a problem**
- After renaming someone, the message shows their old name.

## Channel partners

**What it's for:** distributors, dealers and sub-dealers, and who sits under whom.

**Works**
- **The list:** type, code, parent, area, contact and users. Search and filters; "See the dealers under it" from a distributor.
- **A partner's page:** where it sits, business details, contact and credit terms.
- **Adding a partner:** Admin adds dealers under a distributor; the code and parent can't change later.
- **Payment terms** must be 0 to 365 days.
- **Closing a partner:** it can be closed and reopened. When closed, its users can't sign in.
- **Dealer applications:** a list ready for applications sent by link.

## Marketing material

**What it's for:** order bags, caps, banners and campaign kits, and approve and send them.

**Works**
- A field officer picks items from the catalogue and places an order. It goes to the district manager.
- Admin approves it and records when it was sent.

## Not built yet

These need either the missing server update or test data:
- **Schemes for dealers:** no scheme exists on the test site yet, so scheme targets couldn't be checked.
- **Order and quality settings** in the master lists (lead sources, crops): the columns show "—" until the server update is in place.
- **The dealer's own pages and messages:** not tested, as no dealer sign-in code was available.

## The whole story

This ran in one go in about 3½ minutes, including signing in as each person:

1. The field officer adds **TEST Demo Farmer** with mobile, place, type and system, then marks the lead Contacted, then Qualified.
2. The officer makes a quotation for 300 metres of lateral with an 8% discount and presses **Ask for approval**.
3. The district manager's bell shows "Discount of 8% … waits for your approval". The manager approves it in **Approvals**.
4. The officer sends the quotation without a WhatsApp message (QT/GJ/2026-27/00018) and opens the customer link in a private window: ₹4,002.14 including GST.
5. The officer records **Accepted**. The lead becomes **Won**. Then **Place order**, then **Submit** (SO/GJ/2026-27/00015).
6. The district manager approves, then Accounts (noting "full payment received"), then Dispatch. The officer's bell says "Order … was approved".
7. Dispatch records 100 metres (Partly dispatched), then the remaining 200 (Dispatched).
8. The lead's **Activity** shows the whole story in order: 18 entries, from "created" to "dispatch recorded".
