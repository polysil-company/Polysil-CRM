---
date: 2026-10-02
type: docs
title: "A live test plan for the hosted app, by role and functionality"
dataIds:
  - OBS-002
author: Nakul Srivastava
breaking: false
---

## Before

The automated tests run against the mock backend. Checks against the real backend were done by hand, one feature at a time, and nothing listed what to check on the hosted `integration` app. The approval-limits failure on the dev API (fixed in #46) was found by chance.

## Now

`Docs/Live-Test-Plan.md`: a plan to test the hosted app against the dev API, by a person or by an agent driving a browser.

- **Setup.** What's needed, the rules for a shared database (`TEST` names, no WhatsApp to real customers, approval limits restored), the roles, two screen sizes, what each result means, and the evidence to capture for a failure (screenshot, the REF code, the failing request with its `x-request-id`, console errors).
- **Cases, sections A–Q.** About 100, each with an ID, the Data ID, the role, the steps and the expected result. They cover sign-in, navigation per role, the dashboard, leads, quotations, the customer link, approvals, approval limits, sales orders, dispatch, notifications and messages.
- **Section R.** What isn't built yet, to list rather than test.
- **Section S.** The whole demo story, from a new lead to dispatch, across roles.
- **Two output formats:**
  - a plain-words client walkthrough per functionality (works, works with a problem, doesn't work, not built yet, how to try it);
  - a concise issue report for the developers, with the evidence each failure needs.

`Docs/Tested-Features.md` links to it.

## Discussion

- **The plan is self-contained,** so another agent can run it without this conversation's context.
- **Credentials never go into the repository.** The plan says where they come from and forbids writing them anywhere.
- **The two outputs are kept separate.** The client document has no technical terms; the issue report has all of them.

## Files changed

- `Docs/Live-Test-Plan.md`: new.
- `Docs/Tested-Features.md`: a link to it.

## Tests

Documentation only. Checked that every route, label and rule it names matches the app and `Docs/Tested-Features.md` on `integration`.
