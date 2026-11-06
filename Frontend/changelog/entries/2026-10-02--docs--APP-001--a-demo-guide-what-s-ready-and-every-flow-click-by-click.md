---
date: 2026-10-02
type: docs
title: "A demo guide: what's ready, and every flow click by click"
dataIds:
  - APP-001
author: Nakul Srivastava
breaking: false
---

## Before

What's ready was spread across `Tested-Features.md` (written for developers), the changelog and pull requests. Nothing walked a presenter through the app click by click for a client demo.

## Now

`Docs/Demo-Guide.md`, in plain words, for the team preparing a demo:

1. **What's ready, at a glance:** short pointers per main feature, for everything merged into `integration` up to #47.
2. **What each feature does:** signing in, the dashboard, leads, quotations, approvals and approval limits, sales orders and dispatch, notifications, messages.
3. **Demo flows, click by click, with the exact button names on screen:**
   - what to prepare the day before: logins, two windows, a safe mobile number;
   - a suggested 20-minute order;
   - 14 flows, from signing in to dispatch, including the discount and order approvals shown live in two windows.
4. **Not built yet:** answers for the client's questions.

`Docs/Tested-Features.md` links to it.

## Discussion

- **Labels come from the code.** Button and field names were checked against the components, so the steps match the screen.
- **No WhatsApp to real customers.** The guide says to send WhatsApp only to the presenter's own number.

## Files changed

- `Docs/Demo-Guide.md`: new.
- `Docs/Tested-Features.md`: a link to it.

## Tests

Documentation only.
