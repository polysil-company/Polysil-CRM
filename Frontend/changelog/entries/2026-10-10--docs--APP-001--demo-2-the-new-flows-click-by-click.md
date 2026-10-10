---
date: 2026-10-10
type: docs
title: "Demo 2: the new flows, click by click"
dataIds:
  - APP-001
author: Nakul Srivastava
breaking: false
---

## Before

`Docs/Demo-Guide.md` described the app as it stood for the first client demo (2 October, up to PR #47). Many features have merged into `integration` since then, and the guide listed them under "not built yet":

- lead QR codes and the enquiry page;
- editing, deleting and merging leads;
- tasks and meeting minutes;
- direct orders;
- the dispatch queue;
- complaints with refunds.

## Now

`Docs/Demo-Guide.md` covers everything on `integration` up to PR #84:

- **Part 1** marks each new feature _(new)_ in the at-a-glance list.
- **Part 2** explains lead capture, tidying leads, tasks and meetings, direct orders with the dispatch queue, and complaints.
- **Part 3** adds a 25-minute order for Demo 2, its logins and what to prepare.
- **Part 3b** is Flows 15–22, click by click:
  - a QR code to a lead;
  - finding and tidying leads;
  - the officer's day and the manager's team;
  - a direct order and the dispatch queue;
  - a complaint to QC;
  - the refund through approvals to Accounts.
- **Part 3c** is Flows 23–26 for subsidy, marked to show only after PRs #77, #78, #79 and #86 merge.
- **Part 4** lists only what is still to come.

Flows 1–14 from Demo 1 are unchanged.

## Discussion

- **The labels follow the app.** The buttons named in the steps were checked against the code on `integration` (and the subsidy branches for Part 3c), so the presenter clicks what the guide says.
- **Subsidy is kept apart.** It isn't on `integration` yet, so it has its own part, with the pull requests it waits on.
- **Real customers are never messaged.** The WhatsApp steps (the enquiry code, sending a quotation) use the presenter's own mobile, as in Demo 1.

## Files changed

- `Docs/Demo-Guide.md`

## Tests

None: documentation only. Each flow's tests are named in `Docs/Tested-Features.md`. Rehearse each flow once on the hosted app before the demo, because none has been checked on the dev API by hand yet.
