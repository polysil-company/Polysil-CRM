<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Polysil CRM — rules for every contributor

This is the web frontend of the Polysil Irrigation CRM and dealer management system, built by Loopify Solutions. These rules apply to every contributor, human or AI. Lint rules, git hooks and CI enforce them wherever a machine can check.

When a rule and the code disagree, fix the code — or change the rule here, in the same pull request, with a changelog entry that explains why.

## 1. Read these first

| Before you…            | Read                                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Touch anything visual  | [`src/styles/tokens.css`](src/styles/tokens.css) and [Docs/Design-System.md](Docs/Design-System.md)                    |
| Add a feature or route | [Docs/Frontend-Architecture.md](Docs/Frontend-Architecture.md)                                                         |
| Call an API            | [Docs/Data-IDs.md](Docs/Data-IDs.md), [Docs/Logging.md](Docs/Logging.md), [Docs/Environments.md](Docs/Environments.md) |
| Decide what to build   | [Docs/Frontend-Scope.md](Docs/Frontend-Scope.md) — roles, modules, open questions                                      |
| Try or demo a feature  | [Docs/Tested-Features.md](Docs/Tested-Features.md) — every user story, how far it is tested                            |
| Commit                 | [changelog/README.md](changelog/README.md)                                                                             |

### The design system has two sources — only two

- **[`src/styles/tokens.css`](src/styles/tokens.css)** holds every design decision as a token: colour, type, radius, borders, shadows, spacing, control sizes, stacking layers and motion, for light and dark mode.
- **[Docs/Design-System.md](Docs/Design-System.md)** explains the tokens: what each one is for and when to use it.

Always refer to both. Change a design decision in the token file — and its explanation in the doc — never inside a component. Components use token classes only, so one change there reaches every screen, every story and the docs at once. Lint rejects arbitrary colours, sizes, radii, type, layers and durations.

## 2. Non-negotiables

1. **Type safety.** Strict TypeScript: no `any`, no type assertions, no non-null assertions, explicit return types. Validate every boundary with Zod — API responses, environment variables, URL state and forms.
2. **Tailwind only.** Utility classes built from tokens. No inline styles, no CSS modules, no new CSS files. If Tailwind cannot express something, add a utility to `tokens.css`.
3. **Responsive, always.** Mobile-first. Every screen works from a 360px phone to a wide desktop, with touch targets of at least 44px on touch screens.
4. **Accessible.** Semantic HTML, full keyboard support, visible focus, a name on every icon-only control, and never colour as the only signal. Base UI provides the ARIA wiring — don't fight it.
5. **Light and dark from day one.** Check both for every change.
6. **Every change has a changelog entry** — Before, Now, Discussion, Files changed, Tests. See [changelog/README.md](changelog/README.md).
7. **Every change has a test.** Top-level `describe` names start with the Data ID: `describe("[LEAD-002] NewLeadDialog", …)`.
8. **Every API integration handles every state and edge case** — see §6.
9. **Every feature and every API call logs** through the logger — see §7.
10. **Don't invent business rules.** Thresholds, approval gates and permissions come from the client or the backend. Open questions live in [Docs/Frontend-Scope.md](Docs/Frontend-Scope.md) §10 — ask, and leave `// TODO(DATA-ID): …` in the code.

## 3. Stack

Next.js 16 (App Router, React Compiler, typed routes) · React 19 · TypeScript 6 · Tailwind CSS 4 · shadcn/ui on Base UI · Motion · Zod 4 · TanStack Query 5 and Table 9 · React Hook Form · nuqs · Hugeicons (free set) · Sonner · MSW · Vitest and Testing Library · Storybook 10 · Playwright.

Versions are pinned exactly (`save-exact` in `.npmrc`). Read the documentation for the installed version before using an API — for Next.js, the bundled guides in `node_modules/next/dist/docs/`. The reasons behind each choice are in [Docs/Frontend-Architecture.md](Docs/Frontend-Architecture.md) §1.

## 4. Where code goes

```text
src/
  app/                 Routes only: layouts, pages, loading, error, not-found. Keep them thin.
  components/
    ui/                Primitives — shadcn/ui restyled to tokens. No app knowledge.
    patterns/          Composed building blocks: DataTable, QueryView, StatCard, ErrorState…
    layout/            App shell: sidebar, header, navigation, command menu.
    providers/         Client providers: queries, URL state, motion, tooltips, mocks.
  features/<feature>/
    api/               <feature>.schemas.ts · .api.ts · .queries.ts · .mutations.ts
    components/        The feature's UI
    hooks/, lib/       Feature-only logic
  hooks/               Generic hooks (they may use lib/ only)
  lib/                 Foundation: API client, logger, Data IDs, env, format, auth, theme, motion
  mocks/               MSW handlers and seeded data
  styles/tokens.css    The design tokens
  test/                Test helpers
```

- **Imports flow one way**, enforced by lint: routes (`app`) → shell (`components/layout`, `components/providers`) → `features` → `components/patterns` → `components/ui` → `lib`. Only the mock gate loads mocks.
- **Server Components by default.** Add `"use client"` only for interactivity, and keep client islands small.
- **No data fetching in `useEffect`.** Queries live in `*.queries.ts` and render through `QueryView`.
- **Shareable state lives in the URL** (nuqs): filters, sorting, pagination and open dialogs survive a refresh and can be sent to a colleague.
- **Format with `src/lib/format`** — money in ₹ with lakh and crore, dates in IST, Indian phone numbers. Never call `Intl` or `toLocale*` directly (lint).
- **Named exports only**, except where Next.js or Storybook require a default export.
- **Never leave broken code.** Mark anything incomplete with `// TODO(DATA-ID): …`.

## 5. UI, components and motion

**Reuse before you build:** `components/ui` → `components/patterns` → feature components. To add a shadcn/ui component, view its source (`npx shadcn add <name> --dry-run --view`) and restyle it by hand with the checklist in [Docs/Design-System.md](Docs/Design-System.md) §10 — a plain `shadcn add` installs packages we don't use.

**Icons:** `<Icon icon={…} />` from `@/components/ui/icon`, with the free Hugeicons set. Nothing else renders icons.

**Every state, every component:** default, hover, focus-visible, pressed, disabled, loading, empty, error and success. A skeleton mirrors the exact layout it replaces and is exported beside its component (`StatCardSkeleton`). Async buttons use `useAsyncAction` with `<Button state>` — a circular loader while working, then success or failure, then idle, and never a double submit.

**Motion** follows Emil Kowalski's design engineering rules (the `emil-design-eng` skill):

- Don't animate what people do a hundred times a day or trigger from the keyboard — the command menu uses `motion="none"`.
- `ease-out` for anything entering or responding to input, `ease-in-out` for movement on screen, `ease-drawer` for sheets. Never `ease-in`.
- Interface motion stays at or under 300ms: `duration-press`, `duration-fast`, `duration-base`, `duration-slow`.
- Pressable elements use `press-scale`. Nothing appears from `scale(0)` — start at 95% with opacity.
- Popovers grow from their trigger (`origin-(--transform-origin)`); modals stay centred.
- Animate `transform` and `opacity` only. Reduced motion is honoured globally by the tokens.
- Page transitions are directional: `<Link transitionTypes={["nav-forward"]}>` (or `"nav-back"`), rendered by `PageTransition`.

**Storybook:** every reusable component has a `*.stories.tsx` beside it covering its variants and states. Preview and tweak components in isolation with `npm run storybook`. `npm run test:storybook` renders every story in Chromium and fails on accessibility violations.

## 6. API integration — every call, every state

1. **Register the Data ID** in `src/lib/data-ids/registry.ts`, and in the snapshot in [Docs/Data-IDs.md](Docs/Data-IDs.md), before writing any code.
2. **Write the contract** as a Zod schema in `features/<feature>/api/<feature>.schemas.ts`, agreed with the backend developer.
3. **Call through `apiRequest`** in `src/lib/api/client.ts` — `fetch` anywhere else is a lint error. It sends `x-request-id` and `x-data-id`, applies a timeout, supports cancellation, validates the response and logs the round trip. A response that breaks the schema becomes a `CONTRACT_VIOLATION` error, never a crash.
   - **Authentication is built in.** It sends the access token, refreshes it and retries once after a 401, and adds an `Idempotency-Key` to mutations. Never read, store or pass tokens yourself; choose `auth: "required" | "optional" | "none"`. Mark calls that carry passwords, codes or tokens `sensitive: true`. How sessions work: [Docs/Frontend-Architecture.md](Docs/Frontend-Architecture.md) §8.
   - **Gate on permissions, never on roles:** `useCan("leads", "create")`. Hiding is a courtesy — the backend enforces.
4. **Expose query options** in `*.queries.ts` and mutations in `*.mutations.ts`, with `meta: { dataId }`.
5. **Render all four states with `QueryView`:** pending (a skeleton), empty (why it is empty and what to do next), error (`ErrorState` with a copyable reference, and a retry only when retrying can help) and stale data (keep showing the last data, with a notice).
6. **Handle the edge cases explicitly:** offline and timeout; 401 and 403; 404 (`notFound()`); 409 conflicts; 422 field errors mapped onto form fields; 429; 5xx; empty lists; a page past the end; very long text; missing optional fields; slow responses; double submits; requests cancelled when the user navigates away.
7. **Mock it first** in `src/mocks/handlers`, including the failures. Preview every state from the user menu: the role switcher and the data scenarios (realistic, slow, empty, error, contract).
8. **Test the failure states**, not just the happy path. Tests use MSW, and an unhandled request fails the test.
9. **Integrate on staging** with the checklist in [Docs/Environments.md](Docs/Environments.md) before anything reaches production.

## 7. Logging

- **One logger per file:** `const log = createLogger({ file: "features/leads/components/new-lead-dialog.tsx", dataId: "LEAD-002" })`. `file` is the path under `src/`; lint checks and autofixes it.
- **Format: File → Function → Request → Response.** Wrap handlers in `log.trace("handleCreateLead", () => …)`. `apiRequest` logs requests and responses by itself.
- **Never `console.*`** (lint). Passwords, OTPs, tokens, Aadhaar, PAN, bank details and similar fields are redacted automatically, and phone numbers and emails are masked. Don't log free-text personal data.
- **One variable controls the level:** `LOG_LEVEL` = `debug | info | warn | error | silent`, read at runtime, so production logging can be turned up without a rebuild. A single browser can override it from the console with `polysilLogger.setLevel("debug")`. Details: [Docs/Logging.md](Docs/Logging.md).

## 8. Data IDs — shared with the backend

Every functionality has a Data ID, `DOMAIN-NNN` — for example `LEAD-002`, create lead — used identically by frontend and backend. It appears in the `x-data-id` request header, every log line, the error reference users can copy, test names, changelog entries, commit scopes and branch names, so any bug traces to one functionality on both sides in minutes. IDs are never reused or renumbered. See [Docs/Data-IDs.md](Docs/Data-IDs.md).

## 9. Environments and branches

| Environment           | Branch                             | API                | Mocks          | Default log level |
| --------------------- | ---------------------------------- | ------------------ | -------------- | ----------------- |
| Feature               | `feature/LEAD-002-new-lead-dialog` | MSW mocks          | On             | `debug`           |
| Integration (staging) | `staging`                          | Staging backend    | Off (enforced) | `info`            |
| Production            | `main`                             | Production backend | Off (enforced) | `warn`            |

Work flows from a feature branch → pull request into `staging` → verified against the real backend → pull request from `staging` into `main`. Configuration comes from the environment variables documented in `.env.example`; secrets live only with the hosting provider — never in the repository or `Docs/`. See [Docs/Environments.md](Docs/Environments.md).

## 10. Tests

| Kind                              | Tool                                 | Where                           | Command                  |
| --------------------------------- | ------------------------------------ | ------------------------------- | ------------------------ |
| Unit and component                | Vitest, Testing Library, MSW (jsdom) | Beside the code: `*.test.ts(x)` | `npm test`               |
| Stories: render and accessibility | Storybook with Vitest browser mode   | `*.stories.tsx`                 | `npm run test:storybook` |
| End-to-end smoke                  | Playwright and axe                   | `e2e/`                          | `npm run test:e2e`       |

Test behaviour the way a user meets it — roles, labels and visible text — not implementation details. The browser-based suites need `npx playwright install chromium` once per machine.

## 11. Commits, pull requests and "done"

- **Commits** follow Conventional Commits with a Data ID scope: `feat(LEAD-002): add the new lead dialog` (checked by commitlint). Generic scopes: `deps`, `ci`, `repo`, `docs`, `tooling`, `release`.
- **Git hooks:** pre-commit runs lint-staged, validates the changelog and regenerates `CHANGELOG.md`; commit-msg runs commitlint; pre-push runs the type check and unit tests.
- **Done means:** `npm run verify` passes; a changelog entry exists; tests cover the change; UI changes have stories; the change was checked on a phone and a desktop, in light and dark; the pull request checklist is complete.
- **AI agents** never commit, push, deploy or open a browser unless the developer asks. Report every change with clickable `file:line` links.

### The records every pull request keeps current

Do these without being asked, in the same pull request as the change. A reviewer should never have to ask "is this written down anywhere?".

| Record                                                                                           | Update it when                                                                                         | How                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Changelog entry** — [changelog/](changelog/README.md)                                          | Always: one entry per pull request                                                                     | `npm run changelog:new`, fill every section; review changes on the same branch update the same entry. `CHANGELOG.md` and its index are generated — never edit them.                                                                                                                                                                          |
| **Data IDs** — [registry](src/lib/data-ids/registry.ts) and [Docs/Data-IDs.md](Docs/Data-IDs.md) | A new functionality or endpoint                                                                        | Register before writing code (§6).                                                                                                                                                                                                                                                                                                           |
| **Integration status** — [Docs/Plan.md §9](Docs/Plan.md)                                         | A screen is connected to, or moved off, a real endpoint; the backend ships something the frontend uses | Move the row between §9.1 connected, §9.2 mocked and §9.3 not built; bump the date.                                                                                                                                                                                                                                                          |
| **Backend asks** — [`docs/Backend-Tasks.md`](../docs/Backend-Tasks.md)                           | You need anything from the backend: a missing field or endpoint, a question, a decision, a bug         | A new `BE-NNN` in the checklist and a details block (What, Why, Done when), in that file's format. Never leave a backend question only in chat or a code comment. After every merge into `integration`, read it and pick up what the backend marked done.                                                                                    |
| **Tested features** — [Docs/Tested-Features.md](Docs/Tested-Features.md)                         | A user-facing feature is added or changes                                                              | Add or update its user story: who can do what, the cases checked, and its marks — 🧪 automated, 🌐 end to end, 👀 walked through, 🔌 checked on the real backend. Never mark 🔌 without that check. Say where it lives (`integration` or `PR #n`).                                                                                           |
| **Screenshots** — [Docs/screenshots/](Docs/screenshots)                                          | You check a screen in a browser                                                                        | Save them straight to `Docs/screenshots/<module>/<what>-<viewport>-<theme>.jpg` as JPEG, quality 80 (Playwright `page.screenshot({ type: "jpeg", quality: 80 })`) — small, and no conversion step. Mock data only, never real customer data. Link them from the feature's story. Open only the ones you need to check; saving costs nothing. |
| **Pull request description**                                                                     | Always                                                                                                 | Follow [.github/pull_request_template.md](../.github/pull_request_template.md). A pull request stacked on another says so in its first line and names the merge order.                                                                                                                                                                       |

## 12. Commands

| Command                                                   | What it does                                                          |
| --------------------------------------------------------- | --------------------------------------------------------------------- |
| `npm run dev`                                             | The app on http://localhost:3000 with the mocked API                  |
| `npm run storybook`                                       | Components in isolation on http://localhost:6006                      |
| `npm run verify`                                          | Type check, lint, unit tests and changelog check — run before pushing |
| `npm run typecheck`                                       | Generates route types, then runs `tsc`                                |
| `npm run lint` · `npm run lint:fix`                       | ESLint, with zero warnings allowed                                    |
| `npm run format`                                          | Prettier, including Tailwind class order                              |
| `npm test`                                                | Unit and component tests                                              |
| `npm run test:storybook`                                  | Every story in Chromium, with accessibility checks                    |
| `npm run test:e2e`                                        | Playwright smoke tests                                                |
| `npm run changelog:new -- --type … --data-id … --title …` | Creates a changelog entry                                             |
| `npm run changelog:build`                                 | Regenerates `CHANGELOG.md`                                            |
| `npm run knip`                                            | Finds unused files, exports and dependencies                          |
