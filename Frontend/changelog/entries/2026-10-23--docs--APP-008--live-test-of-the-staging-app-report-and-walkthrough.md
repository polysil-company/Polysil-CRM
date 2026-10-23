---
date: 2026-10-23
type: docs
title: "Live test of the staging app: an issue report and a client walkthrough"
dataIds:
  - APP-008
author: Claude
breaking: false
---

## Before

`Docs/Live-Test-Plan.md` set out 146 cases (§A–§Y) for testing the hosted app against the real backend, but nobody had run them against `polysil-test.pranayx.tech` since the 22 Oct merges. Nothing written down said which screens work on the real backend, which don't, or why.

## Now

- **`Docs/Live-Test-Report.md`, for the developers:**
  - **Results:** 146 cases run as each staff role, on a desktop and on a phone in dark mode. 121 ✅ · 14 ⚠️ · 4 ❌ · 7 ⛔.
  - **19 issues, most serious first,** each with steps, the failing request and its `x-request-id`, and the likely layer. The main ones:
    - The dev API is behind `integration`: BE-023…BE-030 are not deployed.
    - A quotation can be saved with no items (QUOT-004).
    - The State Manager can't open Approval limits, although the API serves them (APP-001 nav gate).
    - The product form's Category and Unit pickers are empty (BE-024).
    - Master lists show no sort order or quality (BE-026).
    - The dashboard's overdue count disagrees with Tasks.
  - **Also in the report:**
    - the sidebar each role sees;
    - the phone pass;
    - §S, the whole client story, run end to end with timings;
    - the blocked cases (no dealer login);
    - every TEST record created, for clean-up.
- **`Docs/Client-Feature-Walkthrough.md`, for the client:** per functionality, in plain words, what works, what works with a problem, what doesn't work yet, and how to try it. It ends with the whole story as numbered steps.
- **Evidence:** `Docs/screenshots/live-test/`, 10 JPEG screenshots, one per ⚠️/❌ that needed one. No passwords or real customer data on screen.

## Discussion

- **Which host:** the developers confirmed in chat to test `polysil-test.pranayx.tech`, although the Caddy config names it staging.
- **The real-WhatsApp API:** the API sends real WhatsApp (`/health` → `"whatsapp":"11za"`). So every TEST lead used the test mobile the developers gave. No quotation was sent on WhatsApp, and no OTP code was sent.
- **Roles:** there is no Regional Manager or dealer login, so the dealer cases are ⛔.
- **The limit changed for M-03** was put back to its original value.
- **Script slip:** a script mistake marked an older test task done. It was reopened at once; the report says so.
- **Not fixed here:** no code changed in this PR. Each issue is for its owner to pick up, under its Data ID:
  - **frontend:** I-03, M-01, B-02, I-05, D-05, Y-03, E-04, X-03, W-05, M-03, J-03, favicon;
  - **backend:** redeploy BE-023…030; the empty-quotation guard; the dashboard's overdue count;
  - **client:** dispatching without stock; whether the State Manager may delete leads.

## Files changed

- `Docs/Live-Test-Report.md` — new: the issue report, all results, and the test data created.
- `Docs/Client-Feature-Walkthrough.md` — new: the plain-language walkthrough.
- `Docs/screenshots/live-test/` — 10 screenshots of the issues.

## Tests

No code changed, so there's no automated test. The report itself is the record of a manual and Playwright run against the live staging app on 22–23 Oct 2026. Re-run a case by following its steps in `Docs/Live-Test-Plan.md`, as the role named, at `https://polysil-test.pranayx.tech`.
