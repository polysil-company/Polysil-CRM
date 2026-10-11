---
date: 2026-10-12
type: docs
title: "A frontend handover: the build process, step by step, and everything left"
dataIds:
  - REPO-001
author: Nakul Srivastava
breaking: false
---

## Before

The way the frontend was built lived only in one long working session:

- how a feature goes from a backend handover to a merged PR;
- the browser walks, screenshots and axe checks;
- how PRs are split and stacked;
- the traps already hit.

`AGENTS.md` holds the rules but not the working loop. `Docs/Plan.md` and `docs/PendingFeatures.md` list what is left, but the second dates from 3 October. A new developer or AI session would have had to rediscover all of it.

## Now

`Docs/Frontend-Handover.md`, linked from the "Read these first" table in `AGENTS.md`, covers:

- **§0–3:**
  - where to start;
  - the project in one page;
  - the user's standing rules for replies, code, security and commits;
  - the toolchain: commands, the mock dev server, Chromium, and CI blocked by billing.
- **§4: the loop every feature followed:**
  - pick and read the contract;
  - branch;
  - Data IDs;
  - permissions;
  - the API layer;
  - a mock with the backend's rules;
  - the UI patterns;
  - the browser walk, including the Playwright and axe helper to paste (the sign-in comes from environment variables);
  - API and UI tests;
  - the records (changelog, Plan §9, Tested-Features, Backend-Tasks, screenshots);
  - the final checks;
  - commit, push and PR;
  - resolving conflicts by merging `integration`.
- **§5–8:**
  - how work was split into PRs and stacked (the subsidy stack as the example);
  - why no subagents were used;
  - a map of the codebase;
  - the traps already hit.
- **§9:** what is built, by area, with its PRs.
- **§10: everything left, in order:**
  - **P0:** the go-live fixes for leads, quotations and orders from the 10 Oct walk.
  - **P1:** backend pick-ups: BE-021, BE-022 with payments, BE-023 and BE-024 when ticked, subsidised orders, subsidy completion.
  - **P2:** 22 modules the backend serves with no screens, each with its handover file, plus the dealer-portal walk.
- **§11:** a first message for the next session.

## Discussion

- **One file, in `Docs/`, beside the other records.** The next session reads `AGENTS.md` first, so the link there is how it finds the handover.
- **No credentials in it.** The walk helper reads the demo sign-in from environment variables, and points to `Docs/Tested-Features.md` for the mock fixture. Real staging logins come from the user.
- **The P0 items summarise the backend's walk-fix handovers.** The file says to read those first, since they are the source.
- **Status is pinned to `integration` at `ed010e1`** (11 October 2026). The file says to check `git log` and `docs/Backend-Tasks.md` for anything newer.

## Files changed

- `Docs/Frontend-Handover.md`: new.
- `AGENTS.md`: a "Continue the build" row in "Read these first".

## Tests

None: documentation only. Checked by hand:

- every file and folder the handover names exists, including `backend/docs/architecture/RBAC.md`, the handover files and the API docs;
- the commands match `package.json`;
- the open asks match `docs/Backend-Tasks.md`;
- the open PRs match GitHub on 11 October.
