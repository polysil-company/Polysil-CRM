# Acceptance Criteria

**This is the granular layer.** [Requirements.md](Docs/Requirements.md) says *what* we agreed to build; this file says *exactly how it must behave*. Under a test-gated delivery model ([ADR-016](Docs/Decisions.md)) it is the most important document in the repository — **an unwritten acceptance criterion is an untested behaviour**.

> **Status:** format defined, three worked examples below. Full authoring for all 73 requirements is Week 0 item 0.14. To be merged against the client's existing detailed requirements document before authoring completes — matched, not duplicated.

---

## How this file is used

```
Requirement (REQ-101)  →  Acceptance criteria (AC-101-01 … AC-101-14)  →  Tests
        │                            │                                     │
    the contract              written BEFORE code                  written by the
                              from the requirement                 PAIRED model
```

**Rules:**

1. Criteria are written **before implementation**, by Opus 5 + Nakul, from the requirement — never from code that already exists.
2. The **implementing model** receives them as its spec. The **test-authoring model** receives the same criteria and writes tests independently, without reading the implementation ([AGENTS.md §2](Docs/AGENTS.md)).
3. Every AC maps to at least one test. An AC with no test blocks the PR.
4. If an AC cannot be written because a business rule is undefined, it is recorded as `⛔ BLOCKED` with its question reference — **not guessed**. That is the mechanism that stops undefined rules being silently invented.
5. Every AC is independently verifiable. "The system should be fast" is not an AC. "p95 under 2s at 500k rows" is.

**ID format:** `AC-<REQ number>-<sequence>` — e.g. `AC-203-07`.

**Each requirement covers five categories.** A requirement whose criteria are all happy-path is not specified, it is sketched:

| Category | What it covers |
|---|---|
| **Happy path** | The intended behaviour |
| **Validation** | What is rejected, and the message shown |
| **Permission** | Who can and cannot, asserted at the database layer |
| **Edge / scenario** | Empty, boundary, large, Unicode, null, concurrent, illegal transition |
| **Failure** | Integration down, network lost, session expired, duplicate webhook |

---
---

# Worked examples

Three examples chosen to show the expected depth across different kinds of requirement: pure business logic, money, and mobile.

---

## REQ-107 · Duplicate Lead Detection

> *Every new enquiry is automatically checked against existing leads and customers by mobile number, email and name + location. Matching records are flagged for the owner to review and merge.*

**Depends on:** [Q14](Docs/Open-Questions.md) *(not blocking — matching rules are proposed below and need client confirmation, not invention)*

### Happy path

| AC | Given | When | Then |
|---|---|---|---|
| AC-107-01 | A lead exists with mobile `9825012345` | A new enquiry arrives with mobile `9825012345` | The new lead is created **and** flagged `duplicate_suspected`, linked to the existing lead with `match_reason = exact_mobile`, confidence `HIGH` |
| AC-107-02 | A lead exists with email `ramesh@x.com` | A new enquiry arrives with the same email, different mobile | Flagged, `match_reason = exact_email`, confidence `HIGH` |
| AC-107-03 | A lead exists: name `Ramesh Patel`, taluka `Gondal` | A new enquiry arrives: name `Ramesh Patel`, taluka `Gondal`, different mobile and email | Flagged, `match_reason = name_location`, confidence `MEDIUM` |
| AC-107-04 | A duplicate is flagged | The lead owner opens the lead | A review panel shows both records side by side with differing fields highlighted |
| AC-107-05 | The owner confirms a merge | Merge is executed | Both records survive as one; **all** activity events, tasks, quotations and complaints from both are retained on the surviving record; the merged record is soft-deleted with a pointer to the survivor |
| AC-107-06 | The owner rejects the match | "Not a duplicate" is chosen | The pair is recorded in `duplicate_dismissed` and **never re-flagged for that pair again** |
| AC-107-07 | Any merge or dismissal occurs | — | An audit entry records actor, timestamp, both record IDs, and the decision |

### Validation & matching rules

| AC | Rule |
|---|---|
| AC-107-08 | Mobile matching normalises first: strip spaces, hyphens, `+91`, and a leading `0`. `+91 98250 12345`, `09825012345` and `9825012345` are the same number |
| AC-107-09 | Email matching is case-insensitive and trims whitespace. Gmail dot-and-plus normalisation is **not** applied *(confirm — [Q14](Docs/Open-Questions.md))* |
| AC-107-10 | Name matching is case-insensitive, whitespace-collapsed, and honorific-stripped (`Shri`, `Mr`, `Smt`) before comparison |
| AC-107-11 | Name + location requires an **exact taluka match**. District-level match alone does not flag |
| AC-107-12 | Detection runs on every creation path — manual entry, website form, WhatsApp, Meta Lead Ads, bulk import. No path may bypass it |

### Permission

| AC | Rule |
|---|---|
| AC-107-13 | Only the lead owner, their manager chain, or Admin may merge. A peer Sales Executive attempting a merge is **rejected at the database layer**, not just hidden in the UI |
| AC-107-14 | A merge across two owners requires manager-level approval and reassigns ownership per [Q16](Docs/Open-Questions.md) ⛔ **BLOCKED — reassignment rule undefined** |

### Edge & scenario

| AC | Given | Then |
|---|---|---|
| AC-107-15 | Three leads share one mobile number | All three are linked as one duplicate cluster, not three unrelated pairs |
| AC-107-16 | An enquiry has **no** mobile and **no** email | Detection falls back to name + location only, and never flags on name alone |
| AC-107-17 | The name contains Gujarati script (`રમેશ પટેલ`) | Matching works on the Gujarati string; a Gujarati name and its Latin transliteration are **not** auto-matched |
| AC-107-18 | Two identical enquiries arrive within the same second | Exactly one duplicate link is created — no race, no double flag |
| AC-107-19 | A lead already merged is targeted by a new merge | Rejected with a clear message; merge chains are not permitted |
| AC-107-20 | 50,000 existing leads | Detection completes in **under 500ms p95** on lead creation, and never blocks the creation itself |
| AC-107-21 | A merged record's ID is requested via a direct URL | Redirects to the surviving record; the old ID never 404s |

### Failure

| AC | Given | Then |
|---|---|---|
| AC-107-22 | The detection job errors | The lead is still created; a `detection_failed` flag is set and retried by the nightly job. **Detection never blocks capture** |

---

## REQ-203 · Instant Quote (GST-calculated)

> *Generate a product-wise, GST-calculated quotation in seconds and share it with the customer instantly.*

**Depends on:** [Q10](Docs/Open-Questions.md) (product master), [Q12](Docs/Open-Questions.md) (invoice vs quote) · **Money requirement — [ADR-013](Docs/Decisions.md) mandates exhaustive unit tests**

### Happy path

| AC | Given | When | Then |
|---|---|---|---|
| AC-203-01 | A Gujarat customer and a Gujarat place of supply | A quote is generated | Tax splits **CGST + SGST**, half the slab rate each |
| AC-203-02 | A Maharashtra place of supply, Gujarat seller | A quote is generated | Tax is a single **IGST** line at the full slab rate. No CGST/SGST lines appear |
| AC-203-03 | A 3-line quote with mixed 12% and 18% products | Totals computed | Tax computed **per line**, then summed. Never computed on the grand total |
| AC-203-04 | Any quote | Displayed or exported | Each line shows HSN code, quantity, UoM, unit price, discount, taxable value, tax rate, tax amount, line total |
| AC-203-05 | An active scheme covers the customer's taluka and a quoted product | Quote generated | Scheme discount applies automatically; the scheme name and its discount are shown as a distinct line, not folded into the price |
| AC-203-06 | Tier price + scheme discount + GST all apply | — | Order of operations is: **tier price → scheme discount → taxable value → GST**. Never GST before discount |
| AC-203-07 | A quote is saved | — | It receives a sequential, gap-free quote number in the configured series |
| AC-203-08 | A quote is generated | The user clicks Share | A PDF is produced and a share link created; opening the link records `Viewed` against the quote and emits a timeline event |

### Money precision

| AC | Rule |
|---|---|
| AC-203-09 | All monetary values stored as `numeric(14,2)`. **Floating point anywhere in the money path is a defect** |
| AC-203-10 | Per-line tax rounds half-up to 2 decimals; the grand total rounds to the nearest rupee, and the rounding difference is shown as an explicit `Round Off` line |
| AC-203-11 | Currency renders in the Indian numbering system — `₹1,00,000.00`, never `₹100,000.00` — in the UI, the PDF, exports and WhatsApp messages |
| AC-203-12 | Line total = `(unit_price × qty) − discount + tax`, and the sum of line totals + round-off equals the grand total **exactly**, asserted by property-based tests over randomised inputs |

### Validation

| AC | Rule |
|---|---|
| AC-203-13 | A quote cannot be saved with zero lines |
| AC-203-14 | Quantity must be a positive number within the product's UoM precision; `0`, negatives, and `1.5` on an integer UoM are all rejected with a specific message |
| AC-203-15 | A discount exceeding the user's approval limit routes to approval rather than being rejected outright ⛔ **BLOCKED — limits undefined ([Q16](Docs/Open-Questions.md))** |
| AC-203-16 | A product without an HSN code cannot be quoted; the error names the product |
| AC-203-17 | Place of supply is mandatory before tax can be computed, because it determines CGST/SGST vs IGST |

### Edge & scenario

| AC | Given | Then |
|---|---|---|
| AC-203-18 | A 200-line quotation | Generates within 3s; the PDF paginates with headers repeated and totals only on the final page |
| AC-203-19 | A ₹4,00,00,000 line value | No overflow, no scientific notation, correct Indian formatting throughout |
| AC-203-20 | A Gujarati customer name and address | Renders correctly in the PDF (embedded Gujarati font), in the share link, and in the WhatsApp message |
| AC-203-21 | The scheme expires between quote creation and acceptance | The quote honours the scheme captured **at creation time**; scheme terms are snapshotted onto the quote, never resolved live |
| AC-203-22 | A product price changes after the quote is sent | The quote retains its original prices. Price is snapshotted, not referenced |
| AC-203-23 | The same quote is submitted twice (double-click, retry) | One quote, one number. Idempotent |
| AC-203-24 | A quote is generated for a customer in a state with no configured tax rule | Rejected with a clear message rather than silently defaulting to CGST/SGST |

### Permission

| AC | Rule |
|---|---|
| AC-203-25 | A Sales Executive may quote only their own leads/customers — enforced by RLS |
| AC-203-26 | A dealer viewing a share link sees the quote **without** logging in, and cannot see any other quote by altering the URL. Share tokens are unguessable and single-quote scoped |
| AC-203-27 | Every quote creation, edit and status change writes an audit entry with old → new values |

### Failure

| AC | Given | Then |
|---|---|---|
| AC-203-28 | PDF generation fails | The quote is still saved; the user sees a retry action. Generation never blocks the record |
| AC-203-29 | WhatsApp send fails | The quote and share link survive; the failure is queued for retry and visible in the timeline as `send_failed` |

---

## REQ-701 · Field visit check-in / check-out (mobile)

> *Mobile app for field sales staff with visit check-in/check-out.*

**Depends on:** [Q21](Docs/Open-Questions.md), [Q25](Docs/Open-Questions.md) (consent) · **Offline-first — the network is assumed absent, not present**

### Happy path

| AC | Given | When | Then |
|---|---|---|---|
| AC-701-01 | A planned visit for today, executive on site | Check-in is tapped | GPS coordinates, accuracy radius, device timestamp and server timestamp are captured; visit status becomes `in_progress` |
| AC-701-02 | Checked in | A photo is taken | The photo is stored with the visit, compressed to ≤ 500KB before upload |
| AC-701-03 | Checked in | Check-out is tapped | Duration is computed from **server** timestamps; notes and outcome are captured; status becomes `completed`, and a timeline event is emitted against the dealer/customer |
| AC-701-04 | A visit completes | — | It appears on the manager's team view within 60s of the device regaining connectivity |

### Offline

| AC | Given | Then |
|---|---|---|
| AC-701-05 | No network at check-in | Check-in succeeds locally and queues. The user sees a clear "will sync" state — never an error, never a silent loss |
| AC-701-06 | The device is offline for 8 hours across 6 visits | All 6 sync on reconnect, in chronological order, with their original timestamps preserved |
| AC-701-07 | The app is force-killed with a queued visit | The queue survives restart |
| AC-701-08 | A sync conflict occurs (server already has the visit) | Resolved idempotently by client-generated visit UUID. No duplicate visits, ever |
| AC-701-09 | The queue holds 200 unsynced items | Sync batches without timing out and shows progress |

### Location integrity

| AC | Rule |
|---|---|
| AC-701-10 | GPS accuracy worse than 100m is recorded as `low_accuracy` and shown to the manager rather than silently trusted |
| AC-701-11 | Location permission denied → check-in is blocked with an explanation of why location is required, and a route to settings |
| AC-701-12 | Mock-location / developer-mode is detected where the OS permits, and flagged on the visit |
| AC-701-13 | Device clock differs from server by more than 5 minutes → the **server** timestamp is authoritative and the skew is recorded |
| AC-701-14 | Check-in more than *N* km from the dealer's registered location is flagged `distance_anomaly` ⛔ **BLOCKED — N undefined ([Q21](Docs/Open-Questions.md))** |

### Consent & privacy

| AC | Rule |
|---|---|
| AC-701-15 | On first launch the user must see and accept a location-tracking notice; the acceptance is stored with timestamp and app version |
| AC-701-16 | Location is captured only during working hours and only for check-in/check-out in Phase 1 scope. Continuous tracking is a separate, separately-consented capability (REQ-702) |
| AC-701-17 | The user can see their own captured location history in-app — transparency is a DPDP expectation, not a nicety |

### Permission & edge

| AC | Given | Then |
|---|---|---|
| AC-701-18 | A Sales Manager opens the app | They see their own visits **and** their team's; an executive sees only their own — same role system as the web, asserted by the generated matrix |
| AC-701-19 | The user is deactivated server-side while offline | On next sync, sync is refused and the local queue is preserved, not destroyed |
| AC-701-20 | A visit is checked in but never checked out by end of day | Auto-flagged `incomplete` and surfaced on the manager's view. The record is never auto-closed |
| AC-701-21 | Battery saver / background restrictions are active | The app detects it and warns the user that sync may be delayed |
| AC-701-22 | A low-end Android device (2GB RAM, Android 10) | The app launches in under 3s and check-in completes in under 2s |
