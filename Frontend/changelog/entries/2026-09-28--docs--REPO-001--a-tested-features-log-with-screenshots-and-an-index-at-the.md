---
date: 2026-09-28
type: docs
title: "A tested-features log with screenshots, and an index at the top of the changelog"
dataIds:
  - REPO-001
author: Nakul Srivastava
breaking: false
---

## Before

What a user can do — and how far each feature was tested — was spread over fourteen changelog entries, pull requests and chat. The screenshots taken while checking screens lived only on the machine that took them. `CHANGELOG.md` had no overview: to find a change you scrolled 865 lines.

## Now

- **`Docs/Tested-Features.md`** — every user story built so far, by module, from the user's side: who can do what, the cases checked, and how far each is tested — 🧪 automated, 🌐 end to end, 👀 walked through in a browser, 🔌 checked on the backend's dev API — with where it lives (`integration` or an open pull request), links to the screenshots and to the changelog entry with the test files. A table at the top gives each module at a glance; the end lists what the backend serves that has no screen yet. Only leads (list, create, open) and staff sign-in are marked 🔌 — everything else still needs its dev-API check before staging, and the file says so.
- **`Docs/screenshots/`** — 29 screenshots from the checks of the lead actions, the quotation screens, the builder, the lifecycle walk-through and the customer's page, by module, as WebP (1.2 MB instead of 3.9 MB as PNG).
- **An index at the top of `CHANGELOG.md`** — one line per change: date, title linking to its entry, type and Data IDs. Generated like the rest, so it never drifts.
- `AGENTS.md` §1 and `changelog/README.md` point to the new file.

## Discussion

- **Why one file for features, apart from the changelog:** the changelog answers "what changed, when and why"; this answers "what works today, and can I trust it" without reading history. It is updated in the same pull request that adds a feature, like `Plan.md` §9.
- **Why not split the changelog into volumes:** nothing is appended to a long file — each change is its own short entry, and `CHANGELOG.md` is rebuilt from them every commit. The index keeps the generated file navigable however long it grows. If it ever gets too long to open, the build can split it by month without touching the entries.
- **Screenshots are WebP**, converted with the `sharp` already installed by Next.js; GitHub shows them inline. Walk-through scripts can save straight into this folder.
- The earlier quotation screenshots were captured before the action bar (#22); the file says so.

## Files changed

- `Docs/Tested-Features.md` — new
- `Docs/screenshots/leads/`, `quotations/`, `public/` — new, 29 WebP screenshots
- `scripts/changelog/lib.ts` — `renderIndex`, rendered at the top of `CHANGELOG.md`; `CHANGELOG.md` regenerated
- `changelog/README.md`, `AGENTS.md` — point to the index and the new file

## Tests

- `scripts/changelog/lib.test.ts` — `[REPO-001]` the index: one row per change, newest first, linking to its entry, marking breaking changes, before the entries
- Every relative link in `Docs/Tested-Features.md` was checked to resolve to a file.
