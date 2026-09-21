# Client Flowchart — verbatim extract

**Source:** `CRM and DMS Flowchart.xlsx`, received 2026-08-17
**Status:** raw extract, version-controlled alongside [BRD-Source.txt](Docs/BRD-Source.txt). Client spelling and abbreviations preserved.

10 sheets. **5 contain content, 5 are empty.** The empty ones are listed at the bottom and matter as much as the filled ones.

---

## Sheet 1 — `Requirement`

**Channel chain (line 1, verbatim):**
> Depot – Distributor – Dealer – sub dealer – Agent – Instit. Sales – Consumer/Employees

**CRM:**
Lead Generation Management · Marketing Activities · Scheme management · Task management · Daily work planner · Reminders (auto mail and msgs) / Notification · Reward System · Services & feedback · Instant Quote · Approvals · In–out MOMs · Gifting on meets category · New leads from SM and other sources (on API base) · Attractive Dashboard · **Language Friendly – not require**

**Dealer Portal (Sub dealer) / Customer Relationship Portal:**
Sales Order · Material Planning (stock management / advance planning) · Dispatch · Pricing & Discounting · Stock Management · Accounts / Payments · Rewards (Giftings) · Rating Systems (regular accounting etc.) · Adding Agent · Complaints & tracking (CRM–DMS portal) · Promotional activities Support · Customer Relationship Portal · Customer Relationship Management — direct mobile-number-based lead and company detail / marketing / branding / rating

---

## Sheet 2 — `Lead management`

### Stage 1 — New lead
New leads with detail (Detail Pending) → **Auto Thank You MSG**

**Sources:** WhatsApp API, Website, Employee (name), Dealer (name), Campaign, Agri Fair/Summit, Farmer Meeting, etc. — *"Add Option require"* (source list must be admin-editable)

**Fields captured:**

| Field | Note |
|---|---|
| Status | |
| Inquiry Media | |
| Inquiry Number | **State-wise, year-wise** numbering |
| Inquiry Type | Commercial / Subsidised / Industrial-Project |
| Farmer–Customer Name | |
| State, District, Taluka/Tehsil, Village/Town | 4-level geography |
| MIS System | |
| Assign Dealer/Distributor | |
| Assign Employee | by default, or assigned by Admin/user |
| Senior Manager | **Auto** (derived from hierarchy) |
| System Material Value | from Quotation |
| Total MIS Cost | from Quotation |

Also: Assign Option · Quotation Option · **"No of lead – Reward Point to Assignee"**

### Stage 2 — Meetings

| Meeting | Purpose | Gift list |
|---|---|---|
| Meeting-1 (with date) | by Call | **Gift List display** |
| Meeting-2 (with date) | **For Survey & Design** | |
| Meeting-3 (with date) | For C & D Understanding | **Gift List display** |
| Meeting-4 (with date) | For Won or Wait | **Gift List display** |
| Meeting-5 (with date) | Follow up | |
| *Add meeting* | | |

### Quotation
Based on sales types · Template set · **Approval**

| Sales Type | Rate logic |
|---|---|
| Commercial | Effective rate selection by state and sales type; Polysil Profile as first page, default and changeable |
| Subsidised | **State-wise, system-wise subsidy — farmer share calculation** |
| Industrial/Project | Polysil Profile first page, default and changeable |

> **"Subsidied — Quotation Templets and Calculation Pending"**
> Quotation Edit/Delete option at each stage

### Stage 3 — Won / Lost, with reason

### If Subsidised — **"State Wise Separate Stages Required"**

**States listed:** GJ · UP · MH · KA · TN-TANHODA · Andhra · TG · RJ · CG (Chhattisgarh) · MP · HR

**Named state owners:** Andhra → Venkateshu · RJ → Nagendra · CG → Nagendra · MP → Sunil Kesari

**Stages 4–17 (one state's flow):**

| Stage | Name |
|---|---|
| 4 | Application Process |
| 5 | Technical Process |
| 6 | Submitted in Department |
| 7 | In Query |
| 8 | WO Issued |
| 9 | TPA Process |
| 10 | Inspection Call |
| 11 | TR Pending |
| 12 | TR Done |
| 13 | FP Submitted |
| 14 | FP Query |
| 15 | FP Cleared |
| 16 | Payment Pending |
| 17 | FP Received from Department |

> *"Add Stage Option require"*
> **"Sub Entries Level Pending and Requiremennt pendinng from our side"** — marked **Detail Pending** against every state column

### Cross-cutting
Tracking and Reports · Edit/Save · Delete · **Performance by No of lead, Sales Amount — hierarchy-wise for all users** · Reward Points · Feedback · **Reward Points Redeem System**

---

## Sheet 3 — `Sales Order`

Sales Order raised from **DMS (Dealers)** or **CRM (Employees)**. One or more leads with quotation. If subsidised, fittings templates added to quotation when making the order. **State-wise.** Attachment option throughout the process.

| Sales Type | Rate logic |
|---|---|
| Commercial | Rate by default effective-date selection, manual change also |
| Industrial/Project | Rate by default effective-date selection, manual change also |
| Subsidised | Quotation by default + templates for fitting items |
| Export | Rate by manual entry |
| Replacement Order | **For complaint only** |

**Approval chain:** Checking & Approval by Managers → **Approval by Account** (with remarks) → **Approval by State Head** (state-wise managers assigned)

**Dispatch:** order-received-date wise → Supply pending / Supply Done / **Short Supply with Items**

Sales Order tracking required for all stages · Tracking and Reports · Edit/Save · Delete · Reward Points · Feedback

---

## Sheet 4 — `Complain HelpDesk`

```
Complaint Entry Form (by DMS & CRM, with attachment)
        ↓
Manager Check & Approval  → Reject / Approve, with remark
        ↓ (if approved)
Quality Checking          → QC Rejection (remark) / QC Approval (remark)
        ↓ (if approved)
Replacement Order by complaint raiser
   — only approved complaints proceed to replacement
   — Supply date and Delivery Challan compulsory in complaint form
```

Complaint tracking required for all stages · Tracking and Reports · Edit/Save · Delete · Feedback

---

## Sheet 5 — `DMS`

Lead Management · Sales Order (Dealer → Company) · Complaint & HelpDesk · **Sub-dealer Add** · **Inventory Add** · **Invoices of Dealer** · Accounting & Payment · Reward points · **Rating System — based on Sales Order + Payment Collection** · Reports · Edit/Save · Delete · Feedback · Reward Points Redeem System · **Won lead Commission Amt Report** · **Won lead Other Commission Report**

---

## Empty sheets — nothing supplied

| Sheet | Corresponding requirements |
|---|---|
| `Daily Work Planner & Task Manag` | REQ-301..305 |
| `Scheme Management` | REQ-201..206 |
| `Reports` | REQ-1201..1211 |
| `Dashboard` | REQ-1001..1002 |
| `Mobile App` | REQ-701..705 — **this is App 3 in its entirety** |

These were already `SPEC` status in [Requirements.md](Docs/Requirements.md). The flowchart confirms the gap rather than closing it.
