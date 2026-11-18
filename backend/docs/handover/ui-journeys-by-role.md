# UI journeys by role, for the Playwright suite

**For:** the frontend track. **From:** the backend's user stories (Requirements.md, 73 REQs) and the permission matrix (RBAC.md section 6).
**Date:** 27 Oct 2026. **Runs against:** staging (`polysil-test.pranayx.tech`), seeded by `seed_demo.py`.

Each journey is one Playwright test. Each one:
- signs in as the role;
- walks the screens in order;
- asserts what the user sees.

The **refusals** at the end of each role matter as much as the journeys. The backend proves each 403 (`tests/rbac/test_route_matrix.py`). The UI test proves the button is not there at all, or that the screen says "not permitted" instead of crashing.

The REQ ids tie each journey to the client's requirements, so the UAT script can cite the test.

---

## Field Officer (`field_officer`)

| # | Journey | Screens | Assert | REQ |
|---|---|---|---|---|
| FO-1 | Create a lead and follow it up | `/leads` → New → `/leads/[id]` → add task | the lead shows in **My leads**; the task shows in `/my-tasks` for today | 101, 301 |
| FO-2 | Quote the lead | `/leads/[id]` → New quotation → `/quotations/new` → lines → Send | status **Sent**; the share link opens `/q/[token]` without signing in | 203, 204, 205 |
| FO-3 | Quote with subsidy | `/quotations/[id]/subsidy` | the subsidy and farmer share show; the figures match the calculator at `/subsidy/calculator` | 501 |
| FO-4 | Mark a lead lost | `/leads/[id]` → Lost → reason and note | the reason is required; the lead leaves the open list | 109 |
| FO-5 | Duty and a visit (Android only) | `/duty` → start → `/visits` → check in with photo → check out | the visit shows on the lead's timeline | 701, 702 |
| FO-6 | Bell and email switches | the bell → open a notice; Profile | the notice opens its record; the two email switches are **hidden** while email is off | 007 |
| FO-7 | Export | `/leads` → Export → CSV | a `.csv` downloads, and its rows match the screen's filters | 1211 |
| FO-8 | Forecast | `/reports/sales-forecast` | either figures or "not enough history"; never a 0 shown as a forecast | 1204 |

**Refused:** a manager's team view (`/team-map`), `/users`, `/approvals` decisions, another officer's lead by URL (it shows "not found", not the lead).

## District Manager (`district_manager`)

| # | Journey | Screens | Assert | REQ |
|---|---|---|---|---|
| DM-1 | Approve a discount | an officer's quotation over the limit → `/approvals` → Approve | the quotation unlocks and the officer's bell rings | 006, 305 |
| DM-2 | Reassign a lead | `/leads/[id]` → Reassign → an officer in the district | the officer sees it; the timeline records it | 101 |
| DM-3 | Team map | `/team-map` → `/team-map/[userId]` | the officers' routes for today; nobody outside the district | 703, 704 |
| DM-4 | Duplicates | `/leads/duplicates` → merge | one lead left; the loser shows under `?stage=merged` | 107 |
| DM-5 | Reports | `/reports/lead-conversion` → PDF | the PDF downloads; on a busy server, "try again in a moment" | 1201, 1211 |

**Refused:** another district's leads and team, `/masters`, `/users/new`.

## State and Regional Manager (`state_manager`, `regional_manager`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| SM-1 | Approve an order above the district limit (`/approvals`) | the order moves to Approved; the dealer's order message is queued | 006 |
| SM-2 | Targets (`/targets`) | target against achievement, live, for the state | 1203 |
| SM-3 | Territory performance by taluka (`/reports/territory-performance`) | the rows roll up to the chosen level | 1208 |

## Admin-Sales (`admin_sales`) and MD (`md_ceo`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| AD-1 | Create a user and a role scope (`/users/new`) | the new user signs in and must change the password | 1301 |
| AD-2 | Price lists (`/products/price-lists/[id]`) | an effective-dated change does not alter a past order | 005 |
| AD-3 | Schemes (`/schemes/new` → `/schemes/[id]`) | the scheme applies on a matching order only | 201, 1104 |
| AD-4 | Recruit a dealer (`/partners/applications`) → applicant link `/dealer-apply/[token]` → decide | approval creates the partner and its login | 1101 |
| AD-5 | Settings (`/settings`), approval limits (`/approval-limits`) | a change takes effect on the next request, not after re-login | 006 |
| AD-6 | Insights (`/reports/insights`) | sentences, no em dashes; each "see more" link opens its report | 903 |

## Account Manager (`account_manager`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| AC-1 | Record a receipt (`/receipts`) and allocate it | the dealer ledger (`/ledger`) balances | 502, 1106 |
| AC-2 | The accounts queue (`/accounts`) | orders waiting on credit, oldest first | 1106 |
| AC-3 | Dealer commission (`/dealer-commissions`) | approve, then pay; you cannot decide on your own record | 501 |

## Dispatch Manager (`dispatch_manager`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| DI-1 | Dispatch an approved order (`/dispatch`) | stock falls (`/stock`); below zero shows in red (GAP-217) | 1105 |

## QC Manager (`qc_manager`) and Support (`support`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| QC-1 | A complaint end to end: `/complaints/new` → register → manager check → QC verdict → remedy | each step's SLA timer shows; the PDF prints | 801, 802, 803 |
| QC-2 | A replacement order from a complaint | the replacement follows its own approval chain | 805 |
| SU-1 | Warranty lookup on a complaint | warranty dates and claim history per unit | 804 |

## Marketing (`marketing`)

| # | Journey | Assert | REQ |
|---|---|---|---|
| MK-1 | A campaign and a QR code (`/campaigns`, `/qr-codes`) | a lead from the QR's public form carries the campaign | 105, 103 |
| MK-2 | Campaign performance (`/reports/campaign-performance`) | cost per lead and per win | 1209 |

## State Co-ordinator (`state_coordinator`) and Board (`board`)

| # | Journey | Assert |
|---|---|---|
| SC-1 | Subsidy applications for their states only (`/subsidy`) | nothing from another state |
| BD-1 | Board: every report and dashboard, read only | no Create, Edit or Delete button anywhere |

## Dealer and Distributor (portal, OTP sign-in)

| # | Journey | Screens | Assert | REQ |
|---|---|---|---|---|
| DL-1 | Place an order | `/portal` → order | tier price with live schemes; credit limit refusal over the limit | 1101, 1104 |
| DL-2 | Follow the order | `/portal` orders | confirmed → dispatched → delivered | 1103 |
| DL-3 | Raise a complaint | `/portal` complaints | registered; the dealer never sees an escalation or who decided | 1110 |
| DL-4 | Ledger and rewards | `/portal` | balance; reward tier | 1106, 1107 |

**Refused:** any staff screen by URL; another dealer's order by id.

## Farmer (consumer portal and public pages)

| # | Journey | Assert | REQ |
|---|---|---|---|
| FA-1 | The website form (`/enquiry`) with a WhatsApp code | an inquiry number; nothing else about the lead | 103 |
| FA-2 | Open a quotation link (`/q/[token]`) and download the PDF | the right quotation; an expired link says so | 204 |
| FA-3 | Rate the service (consumer portal, when switched on) | the rating reaches `/ratings` | 403, 806 |

---

## Notes for the suite

- **Seed:** use `seed_demo.py`'s users. Staging's WhatsApp is the live 11za, so OTP journeys (DL, FA) need a mock-provider box or a test number. The backend's live journey skips the dealer case for this reason.
- **Email (FO-6):** `email_available` is false everywhere until the client gives a mail account (GAP-536). Assert that the switches are hidden; flip the test when it turns on.
- **PDF:** a `503 busy` answer is expected under load. The test should retry once, not fail.
- **Never point a test at production.**
