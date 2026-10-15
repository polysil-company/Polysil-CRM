# Frontend plan from 13 October 2026

What the backend serves that the frontend doesn't use yet, in the order to build it. Any session can pick this up: take the first unticked item, build it, and tick it in the same PR.

_Measured 13 October 2026 against `integration` at `b8632ed`: the backend documents 379 endpoints, and **183 have no frontend**. The full list is in [Frontend-Handover.md §12](Frontend-Handover.md#12-appendix-every-backend-endpoint-without-a-frontend-13-october-2026)._

## How to use this file

1. **Before starting,** read [`AGENTS.md`](../AGENTS.md), then [Frontend-Handover.md](Frontend-Handover.md) end to end, and follow its process (§4) and the user's rules (§2).
2. **Take the first item that is `[ ]`,** top to bottom, unless the user says otherwise.
3. **When you start it,** make a branch from the latest `origin/integration` (`feature/<DATA-ID>-<slug>`). Mark the item `[~]` with the branch name, in that branch's first commit.
4. **When its PR is open,** change `[~]` to `[x]` and add the PR number and date, in the same PR. A reviewer then sees the plan move with the code.
5. **If a session ends part way,** leave the item `[~]` with a note on what is done and what is left, and push the branch.
6. **If something new turns up** (a new backend handover, a new ask, a user decision), add it here under the right tier, with the date.

Legend: `[ ]` to do · `[~]` in progress (branch named) · `[x]` done (PR named) · `[-]` dropped or waiting (reason given).

## Decisions so far

- **13 Oct, from the user:**
  - Build in this order.
  - Subsidised quotations and subsidised orders are **not** part of go-live, so they sit in Tier 3.
  - Keep this file current as each task finishes.
- **Go-live menu:** `RELEASED_NAV` in `backend/scripts/deploy_staging.py` lists the screens the client's deployment shows: Dashboard, Messages, Leads, Quotations, Orders, Approvals, Tasks, Dispatch, Approval limits, Products, Users and Channel partners. Anything outside that list is hidden there (APP-007), but still built and tested.

---

## Tier 1: gaps inside the go-live screens

- [x] **1. Amend an approved order.** PR #124, 13 Oct (`feature/SO-007-amend-order`). Also fixed there: the duplicated §9 paragraph in `Plan.md`.
  - Endpoint: `POST /orders/{id}/amend`.
  - Contract: `backend/docs/handover/settings-amend-reopen-contract.md`, and "Amend after a voided dispatch" in `subsidised-orders-and-small-changes.md`.
  - Data ID: register a new `SO-` id (next free: SO-007).
- [x] **2. Order list filters by area and office.** PR #125, 14 Oct (`feature/SO-001-order-area-filters`). The lead list's Area pill now also serves orders (`source="territories"`).
  - `territory_id` (a comma list; a state selects its districts) and `owner_org_unit_id`, on `GET /orders`, `/orders/stats` and `/orders/export`.
  - Reuse the lead list's area picker.
  - SO-001.
- [x] **3. Order stats and the Accounts queue** (BE-022, done on the backend). PR #127, 14 Oct, stacked on #125: merge #125 first, then retarget #127 to `integration`. It also fixes the menu's permission: `payments`, not `accounts`.
  - `GET /orders/stats`.
  - The queue is `GET /orders?waiting_on=account_manager`, and its badge is stats `waiting_on.account_manager`.
  - ACCT-001: the nav item says "Soon" today, and it is not in `RELEASED_NAV`.
  - Contract: `accounts-queue-order-names.md`. Payments themselves are Tier 4 (item 26).
- [x] **4. Dashboard: two new charts.** PR #128, 14 Oct (`feature/RPT-001-dashboard-charts`). Also adds the `targets` permission module and a target line on `ProportionBar`.
  - `area_by_system: [{system, name, leads, hectares}]`.
  - `targets_by_month: [{month, target, achieved}]`: 6 months, null without a targets permission.
  - Both on `GET /dashboard/overview`. RPT-001.
  - Contract: "Five small changes" in `dealer-recruitment-and-small-changes.md`. Read the `dataviz` guidance before drawing them.
- [x] **5. One conversation by id** (BE-021, done on the backend). PR #131, 14 Oct (`feature/MSG-004-read-one-conversation`). Groups (`participant: null`) are left to item 7.
  - `GET /conversations/{id}`, so the thread header names the colleague after a reload or from a shared link.
  - MSG-002, MSG-004.
- [x] **6. The dealership enquiry type and GSTIN details.** PR #132, 15 Oct (`feature/LEAD-015-dealership-enquiry`). LEAD-015 and CHNL-006.
  - Leads take `inquiry_type: "dealership"`, shown as "Dealership"; such a lead can go from qualified straight to won.
  - `GET /gstin/{gstin}`: prefill the legal and trade names on the channel-partner form when found, and keep them editable.
  - Contract: `subsidised-orders-and-small-changes.md`, "The dealership enquiry type" and "GSTIN details".
  - LEAD-, CHNL-.
- [x] **7. Group chats.** PR #133, 15 Oct (`feature/MSG-006-group-chats`), stacked on #131: merge #131 first, then retarget #133 to `integration`.
  - `POST /conversations/groups`, `PATCH /conversations/{id}`, and the members endpoints (list, add, remove).
  - Contract: `group-chat.md`.
  - Data ID: register a new `MSG-` id (next free: MSG-006).
- [x] **8. Masters admin.** The lists and lead scoring: PR #134, 15 Oct (`feature/MSTR-001-masters-lists`, MSTR-009, MSTR-010; asks BE-026). Offices: PR #135, 15 Oct (`feature/MSTR-011-masters-offices`, MSTR-011), stacked on #134: merge #134 first, then retarget #135 to `integration`.
  - Create and edit the lookups: complaint types, crops, lead sources, lost reasons, meeting types and MIS systems. That is 12 endpoints under `/lookups/*`.
  - Lead scoring: `GET`/`PATCH /lookups/scoring`.
  - Offices: `POST /org-units`, `GET`/`PATCH /org-units/{id}`, close and reopen.
  - The nav item is Admin → Masters (MSTR-001, "Soon"); complaint types are CMPL-008.
  - Contracts: `backend/docs/api/lookups.md`, `org-units.md`, `complaints-contract.md`.

## Tier 2: smaller missing pieces of built modules

- [x] **9. Reopen a closed complaint:** `POST /complaints/{id}/reopen` (`settings-amend-reopen-contract.md`). PR #136, 15 Oct (`feature/CMPL-010-reopen-complaint`, CMPL-010).
- [x] **10. Subsidy applications:** PR #137, 15 Oct (`feature/SUBS-015-reopen-application`, SUBS-015, SUBS-007). The checklist is a read-only Documents tab in Subsidy masters.
  - Reopen a closed file: `POST /subsidy-applications/{id}/reopen` (`subsidy-completion.md` §4).
  - The document types: `GET /subsidy-document-types`.
- [x] **11. One approval request on its own:** `GET /approvals/{request_id}`. Checked 15 Oct: **not needed, nothing to build.**
  - Every approval notification (`approval_requested`) points at the order, the quotation or the complaint, never at the approval itself: `v_type` is `sales_order`, `quotation` or `complaint` in `notify_step` (migrations 023 and 026).
  - Those pages already carry the approval chain (`approval.steps[]`), and the inbox gets the decided request back from its own `POST`.
  - Build it only if a notification ever sends `resource.type = "approval"`; `resourceHref` would then need a screen for it.
- [x] **12. One set of minutes on its own page:** PR #138, 15 Oct (`feature/TASK-007-minutes-page`, TASK-007, which already listed the endpoint). "From meeting minutes" on a task links to `/tasks/minutes/{id}`. `GET /minutes/{id}` (`tasks-and-planner-contract.md`).
- [x] **13. Check the screens against three handovers,** which the endpoint count can't see. Checked 15 Oct:
  - Exports: all eight lists have Download Excel (`export_too_large` handled; no button on the complaints "Waiting on me" queue). Nothing to do.
  - QR codes: Active/Off chip and Edit exist. Assign: the response replaces the lead, so the new office shows. Nothing to do.
  - Quotation print: the PDF opens as a link, so mixed orientation is fine; the one-discount-column mirror is optional and left.
  - **Gap: dormant leads** (banner, Reopen to `dormant_from_stage`, Mark lost): PR #139, 15 Oct (`feature/LEAD-007-dormant-leads`).
  The handovers:
  - `list-exports.md`: every list it names has an export.
  - `lead-small-gaps-contract.md`: dormant leads, and assigning moves the lead's office.
  - `quotation-print-format.md`: optionally, the quotation page shows one discount column, as the PDF now does.
- [x] **14. Andhra Pradesh in the calculator** (FS-063, `andhra-pradesh-subsidy.md`). PR #140, 15 Oct (`feature/SUBS-002-scheme-inputs`): every scheme's `inputs` (CG, RJ, UP, AP), AP's null matrix ids and state GST, and the scheme picker's default fixed.
  - Checked 15 Oct: the calculator reads none of the config's `inputs`, so CG, RJ and UP's fields (`state-subsidy-formulas.md`) are missing too, and an AP drip result (`regular_matrix_id: null`) would fail the response schema. This item builds every scheme's inputs from the config.
  - Drip asks for "Guided cost (from the AP MIP portal)" and "Fittings and accessories", read from `GET /subsidy/config?scheme=AP`.
  - Not checked yet whether the calculator builds these inputs from the config by itself.
- [-] **15. Staging checks (🔌) for #111, #112 and #113:** waiting on staging credentials from the user (asked 15 Oct).
  - a real `.xlsx` import into a draft price list and into a quotation;
  - add a distributor, a dealer under it, and close a partner that has a user;
  - attach a PDF and a HEIC photo, then open both.

  Follow `Docs/Live-Test-Plan.md`. Credentials come from the user, never from a file, and no WhatsApp messages go to real customers.

## Tier 3: subsidised quotations and orders (not go-live, per the user on 13 Oct)

- [x] **16. Subsidised quotation.** PR #141, 15 Oct (`feature/QUOT-013-subsidised-quotation`, QUOT-014), stacked on #140: merge #140 first, then retarget #141 to `integration`.
  - `PUT /quotations/{id}/subsidy` and `GET /quotations/{id}/subsidy/calculation`.
  - Contract: `subsidised-quotations.md`.
- [x] **17. Subsidised order.**
  - [x] **17a. From a subsidised quotation.** PR #142, 15 Oct (`feature/SO-008-subsidised-order`, SO-008), stacked on #141. Also: the order's Subsidy card, editing a draft's amounts, and Edit items keeping a fixed type.
  - [x] **17b. Typed in directly**, with the multi-lead picker (1 to 50) and the amounts on the new-order screen. PR #143, 15 Oct (`feature/SO-008-direct-subsidised-order`), stacked on #142. Edit the subsidy also adds and removes leads.
  - `PUT /orders/{id}/subsidy`, and the "Subsidised" type on the new-order screen and the order page.
  - Contract: `subsidised-orders-and-small-changes.md`.
- [~] **18. Subsidy completion** (`subsidy-completion.md`). Started on `feature/SUBS-016-subsidy-completion`, stacked on #143. Reopening a closed file (its part 4) is already in #137:
  - the farmer's share paying a subsidised order;
  - the dispatch date on an application;
  - the new bell notifications;
  - Sprinkler areas between table steps.

## Tier 4: modules with no screens yet

In the handover's order of value to the client (§10, P2). Each has a contract in `backend/docs/api/` and a handover in `backend/docs/handover/`.

- [ ] **19. Dealer recruitment** (17 endpoints): staff screens, and the public applicant page `/dealer-apply/<token>`. `dealer-recruitment-and-small-changes.md`.
- [ ] **20. Territories admin** (4). `backend/docs/api/territories.md`.
- [ ] **21. Company settings** (2). `settings-amend-reopen-contract.md`.
- [ ] **22. Reports, and the 360° lead view** (9). RPT-002. `reports-contract.md`, `when-a-sale-counts.md`.
- [ ] **23. Targets and achievement** (3). `targets-contract.md`.
- [ ] **24. Schemes and promotions** (6, plus `GET /orders/{id}/schemes`). SCHM-001. `schemes-contract.md`.
- [ ] **25. Reward points** (19), **and dealer commission and TOD** (12). `rewards-contract.md`, `dealer-commission-contract.md`.
- [ ] **26. Payments, partner credit and the dealer ledger** (8). `payments-contract.md`. It goes with item 3.
- [ ] **27. Marketing material ordering** (11), **and campaigns** (5). MKT-001. `marketing-material-contract.md`, `campaigns.md`.
- [ ] **28. Stock** (7): warehouses, availability on the order form, and the stock list. `stock-contract.md`.
- [ ] **29. Warranty tracking** (3). `warranty.md`.
- [ ] **30. Export and sample orders,** with the seller GSTINs and their LUTs (3). `export-sample-orders-contract.md`.
- [ ] **31. Dealer tasks** (tasks for partner users). `dealer-tasks-contract.md`.
- [ ] **32. Complaint holidays and escalation** (3). `complaint-holidays-escalation.md`.
- [ ] **33. The customer record** (4). `customer-record.md`.
- [ ] **34. Ratings, and the consumer portal** (4 + 8). `ratings-contract.md`, `consumer-portal.md`.
- [ ] **35. Field tracking map screens** (16; the Android app is separate). `field-tracking-contract.md`.
- [ ] **36. The in-app assistant** (2). `in-app-assistant.md`.
- [ ] **37. A consolidated order** from several quotations of one dealer: `POST /orders` with several `quotation_ids` (`orders-api-contract.md`).
- [ ] **38. The dealer portal walk:** sign in as `dealer`, `distributor` and `sub_dealer`, walk every screen, and fix what leaks or breaks.

## Waiting on someone else

- [-] **BE-023:** a `lead_id` filter on `GET /subsidy-applications`, for the subsidy card on a lead. Open on the backend.
- [-] **BE-024:** `GET /lookups/product-categories` and `/lookups/uoms` for the product form. Open on the backend.
- [-] **BE-025:** `record_type` on `GET /documents/types`, so a lead isn't offered the dealer-application types. Open on the backend.
- [-] **CHNL-002, the client:** should a distributor or dealer add the next type down from the portal ("My dealers")? The screens are staff only today.
- [-] **F-12, the user:** files on a complaint can't be added after the QC verdict. Is that meant?

## Optional polish

- [ ] A "Deleted leads" view with `deleted=true`, for `leads.delete` holders.
- [ ] The mock's quotation pricing reads `mockDb.products` and the in-force price list, rather than the six `MOCK_PRODUCTS`.
- [ ] Dark mode: a hovered row with an avatar fails colour contrast (the avatar's 5% white background on `bg-accent`; initials below 4.5:1). Seen in New message and New group (#133). A token change in `tokens.css`, so it reaches every screen.

## Done

Move nothing here: tick items where they are. This section lists what was finished before this plan, for context.

- **12 Oct, #109:** go-live fixes from the 10 Oct walk (APP-006).
- **13 Oct:**
  - #111: Excel import and price lists by sale type (MSTR-007, MSTR-008).
  - #112: the channel partners admin (CHNL-001…005).
  - #113: documents on leads, quotations, orders and dispatches (DOC-001…003).
  - #114: #112 and #113 brought into `integration`.
  - #118: the release menu (APP-007).
- **14 Oct, #126 (not a plan item):** a dialog's close timer could start after the dialog had gone, failing CI at random (`window is not defined`). One `useCloseAfterSuccess` hook now serves eleven dialogs (APP-003); ported into #124.
