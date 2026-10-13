# Frontend handover: how this app was built, and what is left

This is for the next developer or AI session that picks up the Polysil CRM web frontend. It covers:

- how every feature so far was built, step by step;
- the checks, tests and browser walks that go with each one;
- how features were split into pull requests;
- the traps already hit;
- everything still left to build, in order.

Read it once, end to end, before writing code. Then keep it open.

_Written 11 October 2026, against `integration` at `ed010e1` (PR #95 merged). The status in §9 and §10 is as of that commit; check `git log origin/integration` for anything newer._

---

## 0. Start here (the first 15 minutes)

1. **Read the rules,** in this order:
   - [`Frontend/AGENTS.md`](../AGENTS.md): the contributor rules (non-negotiables, folder layout, API rules, records per PR);
   - this file;
   - [`Docs/Plan.md` §9](Plan.md): what is connected, and what is still unbuilt;
   - [`docs/Backend-Tasks.md`](../../docs/Backend-Tasks.md): every ask to the backend, ticked when done.
2. **Fetch and branch from the latest `integration`:** `git fetch origin && git checkout -B <branch> origin/integration`. Never branch from `main` or `staging`.
3. **Check what the backend shipped since the date above.** Run `git log origin/integration --oneline`, read any new file in `backend/docs/handover/`, and look for newly ticked boxes in `docs/Backend-Tasks.md`. A ticked box is work for you: pick it up (§4.1).
4. **Install and prove the toolchain** (§3): `npm ci`, then `npm run verify` on a clean checkout. It must pass before you change anything.
5. **Take the next item** from §10, top first, unless the user says otherwise.

---

## 1. The project in one page

- **Monorepo** `polysil-company/polysil-crm`, git root = the repository folder:
  - `Frontend/`: this Next.js app. Every frontend rule lives in `Frontend/AGENTS.md`.
  - `backend/`: the API, built by a separate backend developer (also using Claude). Its contract for us is in two places:
    - `backend/docs/api/*.md`: generated, one file per module, the source of truth for request and response shapes;
    - `backend/docs/handover/*.md`: written notes per feature, saying what the frontend should build and the rules behind it.
  - `docs/Backend-Tasks.md`: the to-do list between the two sides (§4.12).
  - `docs/CI-CD.md`, `docs/PendingFeatures.md`: CI, and an older backlog with plans for the mobile app, website and assistant.
- **Branches:**
  - Every PR targets `integration`.
  - `integration` → `staging` (PR #11) → `main` (PR #7). These are standing PRs: never touch them.
  - Feature branches are named `feature/<DATA-ID>-<slug>`, for example `feature/MSTR-004-product-master`.
  - Docs branches are named `docs/<slug>`.
- **Stack:** Next.js 16 (App Router, typed routes, React Compiler), React 19, TypeScript strict, Tailwind 4 with tokens only, shadcn/ui on Base UI, TanStack Query 5, Zod 4, nuqs, MSW mocks, Vitest with Testing Library, Playwright with axe, Hugeicons. See AGENTS.md §3.
- **Data IDs** (`DOMAIN-NNN`, for example `LEAD-002`) identify every functionality on both sides. They appear in:
  - the registry, `src/lib/data-ids/registry.ts`, plus its snapshot in `Docs/Data-IDs.md`;
  - every log line and the `x-data-id` header;
  - test names (`describe("[LEAD-002] …")`);
  - commit scopes, branch names and changelog entries.
- **The people:**
  - **The user** is Nakul Srivastava, frontend lead, product and UX minded. He merges the PRs.
  - **The backend developer** works in `backend/` and answers through `docs/Backend-Tasks.md` and the handover files.
  - **The client** is Polysil Irrigation (Gujarat), going live first on **leads, quotations and sales orders**.

---

## 2. The user's standing rules (follow every one)

These come from the user and held for the whole build. Break none of them.

**Replies:**

- Start every reply with "Radhe Radhe!" (or "Jai Shree Krishna!" and the like) and end with "Hari Bol!".
- Treat the user as a capable developer. Be practical, and explain a genuinely new concept from first principles.
- End every coding task with a **"What I changed"** section in exactly this format:
  `[FileName.tsx (lines 51-81)](Frontend/path/FileName.tsx:51): what changed, plus a risk note if useful.` Group a file's non-contiguous ranges, and list the files that might affect other screens.
- Before calling anything done, show that `npm run verify` passed: typecheck, eslint with zero warnings, tests and the changelog check.
- **Never create an Artifact** (a hosted page) without asking first: it costs tokens.
- **Don't spawn subagents** unless the user asks (§6).
- When requirements are fuzzy, state the assumption and go on. Ask only blocking questions.

**Code:**

- Strict TypeScript: no `any`, no type assertions (`as`), no non-null assertions (`!`), explicit return types everywhere.
- Validate with Zod at every boundary: API responses, URL state and forms.
- Tailwind token classes only (`src/styles/tokens.css`): no inline styles, no arbitrary values, no new CSS.
- Mobile-first, from 360 px wide, with 44 px touch targets.
- Accessible: semantic HTML, labels, keyboard support, never colour alone.
- Light and dark mode from day one.
- Every state handled: loading, empty, error, disabled, success, and phone.
- **Don't invent business rules.** Thresholds, permissions and approvals come from the backend or the client. If unsure, leave a `// TODO(DATA-ID): …` and raise a `BE-NNN` ask.
- Before adding a library, compare free and open-source options, and pin the exact version.

**Security and process:**

- **Credentials never go in any file, screenshot, report or commit.** That includes real staging logins. The mock demo sign-in in `Docs/Tested-Features.md` is a mock fixture, not a credential; it is fine.
- **Never send WhatsApp messages to real customers** when testing against staging.
- If you change approval limits on staging to test something, **restore them** afterwards.
- No model names or IDs in any repository artifact (code, commits, PRs, docs).
- **Commit message trailers:** end every commit with the two lines the session's system reminder gives, which were:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: <this session's URL>
  ```
  Use whatever the new session's own instructions specify; the format of the trailer lines comes from there, not from here.
- **PR descriptions:** end with the attribution lines the session specifies, typically `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, a blank line, then the session URL.
- **GitHub comments** end with a blank line, `---`, then `_Generated by [Claude Code](https://claude.ai/code)_`.

---

## 3. Toolchain and environment

- **Node:** in the cloud container used so far, Node comes from nvm and is not on `PATH` by default. Prefix shell commands with:
  ```bash
  export NVM_DIR=/opt/nvm; . /opt/nvm/nvm.sh
  ```
  On a normal machine, use the Node version in `.nvmrc` or `package.json` `engines`.
- **Commands** (run from `Frontend/`):

| Command | What it does | When |
| --- | --- | --- |
| `npm ci` | Install exactly the lockfile | Once per checkout |
| `npm run typecheck` | `next typegen` + `tsc --noEmit` | After every few files |
| `npx eslint --fix <paths>` | Lint and autofix: import order, logger file paths, and more | After writing files; re-read what it changed |
| `npm run verify` | typecheck + lint + all unit tests + changelog check | Before every commit; takes about 10 min |
| `npx vitest run --project unit <path>` | One feature's tests | While working |
| `npm run knip` | Unused files and exports | Before the PR |
| `npx prettier --check .` (or `--write <paths>`) | Formatting | Before the PR |
| `npm run build` | Production build | Before the PR |
| `npm run changelog:new -- --type feature --data-id X --title "…"` | New changelog entry | Once per PR |
| `npm run changelog:build` | Regenerates `CHANGELOG.md` | After editing an entry, and after every merge |

- **Typed routes:** `PageProps<"/products/price-lists/[listId]">` and `href` types come from `.next/types`. If tsc complains about a route that exists, run `rm -rf .next/dev/types && npm run typecheck`.
- **Git hooks:** pre-commit runs lint-staged and the changelog. pre-push runs typecheck and the unit tests, so a push takes a few minutes. Give it a 10-minute timeout.
- **The dev server with mocks**, on a port of its own:
  ```bash
  NEXT_PUBLIC_APP_ENV=development NEXT_PUBLIC_API_MOCKING=enabled npx next dev -p 3100 > /tmp/dev.log 2>&1
  ```
  - Run it in the background. The first compile of a page is slow, so loop on `curl` until it answers. `/products` answers 307 (to sign-in) when the server is up.
  - Stop it with the background-task stop tool, or `kill` its PID. **Don't use `pkill -f "next dev -p 3100"` from the same shell command line:** the pattern matches the shell running it and kills your own command.
  - `NEXT_PUBLIC_API_MOCKING=partial` sends everything to the real dev API except what is listed in `unbuiltHandlers` (`src/mocks/handlers/index.ts`).
- **The dev API and staging:** `backend/docs/handover/dev-api-access.md` and `Docs/Environments.md`. Real logins are never written down: ask the user.
- **Chromium for Playwright** is pre-installed at `/opt/pw-browsers/chromium` in the cloud container. Don't run `playwright install` there.
- **GitHub:** in the cloud container, use the GitHub MCP tools (`mcp__github__create_pull_request` and so on) to open PRs. `gh api repos/polysil-company/polysil-crm/pulls/<n>` works for reading state.
- **CI:** GitHub Actions has been **blocked by billing** since early October. PRs show "unstable" because no checks run, so your local `verify`, `knip`, `prettier --check` and `build` are the gate. Say so in each PR.

---

## 4. How one feature is built, step by step

This is the exact loop every feature went through: leads, quotations, orders, tasks, complaints, subsidy, users, products. Follow it in order.

### 4.1 Pick and scope the work

- **Sources, in priority order:**
  1. The user's ask.
  2. Boxes the backend has newly ticked in `docs/Backend-Tasks.md`.
  3. New files in `backend/docs/handover/`.
  4. `Plan.md` §9.3, served but not built.
  5. §10 below.
- **Read the contract fully before any code.** That means the handover file, the generated `backend/docs/api/<module>.md` (exact fields, enums, status codes, error codes), and `backend/docs/architecture/RBAC.md` for permissions. Check the backend's tests or migrations when an enum or a seed matters, for example product categories in migration 010.
- **Read one similar, finished feature** and copy its patterns. Good references:

| Kind of screen | Copy from |
| --- | --- |
| Filtered list with cursor paging | `features/complaints/components/complaints-list.tsx` |
| Offset-paged list with a pager | `features/products/components/product-catalogue.tsx` |
| Detail page with actions | `features/complaints/components/complaint-detail.tsx`, `features/orders/components/order-detail.tsx` |
| Dialog form | `features/lead-capture/components/qr-codes.tsx` (react-hook-form), `features/products/components/product-dialog.tsx` (plain state) |
| Tabs in the URL | `features/products/components/product-master.tsx` with `hooks/use-product-master-params.ts` |
| Admin people screens | `features/users/` |
| Excel download | `components/patterns/download-excel-button.tsx` and its uses |

- **Split into PR-sized slices** (§5) and write the slices down as tasks.

### 4.2 Branch

- Standalone: `git checkout -B feature/<ID>-<slug> origin/integration`.
- Stacked on an unmerged PR: branch from that PR's branch (§5).

### 4.3 Register the Data IDs first

- Add each ID to `src/lib/data-ids/registry.ts` and to the snapshot table in `Docs/Data-IDs.md`, with its domain, title, owner, status and endpoints. Copy the neighbouring rows' shape.
- IDs are never reused or renumbered. Take the next free number in the domain, and grep the registry first.

### 4.4 Permissions

- Module codes the backend uses go in `MODULE_CODES` (`src/lib/auth/permissions.ts`), for example `products` and `pricing` (from RBAC.md §6).
- Grant them per role in the mock (`src/mocks/data/permissions.ts`), exactly as RBAC.md says.
- Gate the UI with `useCan(module, action)`. Hooks are called unconditionally. Hiding is a courtesy, because the backend enforces it.
- Partner users (dealers) are filtered by the nav's `audience: "staff"`. Route guards for direct URLs are still open (§10, F-8).

### 4.5 The API layer: `src/features/<feature>/api/`

1. **`<feature>.schemas.ts`**
   - Zod schemas of the wire shape, exactly as `backend/docs/api` says.
   - A `.transform` into a camelCase screen type with an explicit `interface`.
   - Request body interfaces in snake_case.
   - Export `…Wire` input types only if the mock imports them; knip flags the rest.
   - Money and quantities stay decimal **strings** end to end.
2. **`<feature>.api.ts`**
   - One function per endpoint, through `apiRequest({ dataId, logger, fn, path, method, query, body, idempotencyKey, schema, signal })`.
   - Mutations take an `idempotencyKey`. Use `schema: z.undefined()` for a 204.
   - Use `apiDownload` for files, and `sensitive: true` for anything carrying a password or code.
3. **`<feature>.queries.ts`**
   - A key factory (`fooKeys.all`, …).
   - `queryOptions` per read, with `meta: { dataId }`.
   - Paged lists use `placeholderData: keepPreviousData`.
4. **`<feature>.mutations.ts`**
   - `useMutation` hooks with `mutationKey` and `meta`.
   - Invalidate the feature's `keys.all` on success, plus other features' keys the change affects (an order affects its lead, for example).
   - Multi-call flows live here. For example, "save rates" reads all the existing rates, merges, then PUTs, because the endpoint replaces everything.

### 4.6 The mock: `src/mocks/`

The app and every test run against MSW mocks, so the mock must behave like the backend:

- **`data/<feature>.ts`:** seed data. Reuse ids from other mocks where records relate. For example, the product mock reuses the quotation mock's six product ids, and the "GJ 2026-27" price list reuses its id.
- **`db.ts`:** add the tables to the in-memory db and to `resetMockDb()`.
- **`handlers/<feature>.ts`:** one handler per endpoint, implementing the backend's rules:
  - permission checks returning 403;
  - a required `Idempotency-Key` on mutations;
  - 404s, 409 conflict codes and 422 `fields`;
  - paging metadata.
  
  Start each handler with `applyScenario()`, so the user-menu data scenarios (slow, empty, error, contract) work.
- **Register it** in `handlers/index.ts`. When two features serve the same path, remove the old handler (as the quotation mock's `GET /products` was).
- **Role switching:** the mock reads the role from localStorage `polysil:mock-role` (`writeMockRole` in tests). Staff role codes: `employee`, `district_manager`, `state_manager`, `regional_manager`, `admin`, `account_manager`, `dispatch_manager`, `qa_manager`. Partner codes: `distributor`, `dealer`, `sub_dealer`.

### 4.7 The UI: `src/features/<feature>/components/` and routes

- **Building blocks:**
  - `QueryView` (pending, empty and error states);
  - `EmptyState` (its `icon` prop is required);
  - a `…Skeleton` exported beside each list and page;
  - `SearchField`, `FilterPill` and `SingleFilterPill`;
  - `Badge` (variants: neutral, primary, success, warning, danger, info, highlight, outline);
  - `RelativeDate`, `DownloadExcelButton`, `Dialog` with `DialogContent size="sm|md|lg"`;
  - `Field`, `FieldLabel`, `FieldError` and `FieldDescription`, `Select` (Base UI, `items` prop), `Checkbox`, `ToggleGroup`, `Tabs`;
  - `TerritoryPicker` (`levels={["state"]}` and so on).
- **Async buttons:** `useAsyncAction({ action, logger, fn, dataId, onSuccess, onError })` with `<Button state={x.state} loadingLabel successLabel errorLabel>`. Pair it with `useIdempotencyKey()`: call `keyFor(body)` per attempt and `reset()` on success.
- **Errors:**
  - Map a 422 onto fields with `readFieldErrors`.
  - Turn named 409 codes into sentences; `features/products/lib/refusals.ts` is a template.
  - Anything else goes through `toUserFacingError(error).title`.
  - A 404 on a detail page calls `notFound()`.
- **State that should survive a refresh** (filters, page, tab, open view) goes in the URL with nuqs: a `use-<feature>-params.ts` hook built on `useQueryStates`.
- **Routes** stay thin: a `page.tsx` with `PageTransition` and `PageContainer`, a `loading.tsx` rendering the skeleton, `metadata` with a title, and `params` read through `PageProps<"/path/[id]">`.
- **Navigation:** add the item to `src/components/layout/navigation.ts` with `id`, `label`, `description` (shown in the top bar), `icon` (check it exists in `@hugeicons/core-free-icons` and isn't already used), `module`, `audience`, `dataId` and `href`. Items without `href` show as "Soon".
- **Formatting:** only `src/lib/format` (`formatInr`, `formatFullDate`, `formatCount`, `todayInIndia`, `shiftCalendarDay`, …). Never `Intl` or `toLocale*`.
- **Logging:** one logger per file: `createLogger({ file: "features/x/components/y.tsx", dataId })`. Lint fixes the path.
- **Layering** (lint enforces it): features may not import `components/layout`, and `components/patterns` may not import features. Move shared bits down a layer, as `BrandMark` moved to patterns.

### 4.8 Check early

After every two or three files, run `npm run typecheck` and `npx eslint --fix <your paths>`, and re-read what the autofix changed (§8).

### 4.9 The browser walk, with screenshots

Every feature was clicked through in real Chromium on the mock backend before writing tests. This catches wrong copy, layout bugs and real bugs that unit tests miss: for example "gujarat · dealers" printed in lower case, or an HSN history line duplicating the heading.

1. Start the dev server (§3).
2. Write a Playwright script in a scratch folder (not in the repo), using the helper below.
3. Walk each user story, the mistakes included:
   - submit an empty form;
   - trigger a duplicate or conflict;
   - try a forbidden role (`employee`, or `dealer` for partner views);
   - check a phone at 390×844 in dark mode and a desktop at 1440×1000 in light.
4. Save screenshots straight to `Frontend/Docs/screenshots/<module>/<what>-<viewport>-<theme>.jpg` as JPEG, quality 80. Mock data only.
5. Run axe on every screen: the target is "none". Log console errors too; an expected 409 from a deliberate duplicate is fine.
6. **Open the key screenshots and look at them.** Fix anything off, then rerun.

**The helper.** Paste it at the top of each walk script. It signs in through the real form; the mock accepts the demo sign-in listed in `Docs/Tested-Features.md`. Pass it in as environment variables rather than writing it into the script:

```js
// walk.mjs — run from Frontend/: DEMO_EMAIL=… DEMO_PASSWORD=… node /path/walk.mjs Docs/screenshots/<module>
import { chromium } from "./node_modules/playwright/index.mjs"; // use an absolute path if the script lives elsewhere
const { default: AxeBuilder } = await import("./node_modules/@axe-core/playwright/dist/index.mjs");
const OUT = process.argv[2];
const BASE = "http://localhost:3100";
const shot = (page, name, full = false) =>
  page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 80, fullPage: full });
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" }); // drop executablePath off the container
const axeOf = async (page) =>
  (await new AxeBuilder({ page }).exclude("nextjs-portal").analyze()).violations
    .map((v) => `${v.id}(${v.impact}): ${v.nodes[0]?.target}`).join(" | ") || "none";

/** Signs in as a mock role and lands on `next`. Roles: admin, employee, state_manager, dealer, … */
async function open(role, next, viewport = { width: 1440, height: 1000 }, scheme = "light") {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme, acceptDownloads: true });
  await ctx.addInitScript((r) => {
    if (!window.localStorage.getItem("polysil:mock-role")) window.localStorage.setItem("polysil:mock-role", r);
  }, role);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !m.location().url.includes("favicon")) errors.push(m.text().slice(0, 200)); });
  await page.goto(`${BASE}/sign-in?method=staff&next=${encodeURIComponent(next)}`);
  await page.getByRole("textbox", { name: "Work email" }).fill(process.env.DEMO_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL(new RegExp(next.replace(/[?]/g, "\\?")), { timeout: 90000 });
  return { ctx, page, errors };
}

/** A screenshot of the whole scrolling content, for long lists and forms. */
async function tall(page, name) {
  const extra = await page.evaluate(() => {
    let best = 0;
    for (const el of document.querySelectorAll("*")) {
      const s = getComputedStyle(el);
      if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 4) best = Math.max(best, el.scrollHeight - el.clientHeight);
    }
    return best;
  });
  const size = page.viewportSize();
  await page.setViewportSize({ width: size.width, height: size.height + extra });
  await page.waitForTimeout(500);
  await shot(page, name);
  await page.setViewportSize(size);
}

// ── the walk ──
{
  const { ctx, page, errors } = await open("admin", "/products");
  await page.getByRole("list", { name: "Products" }).waitFor({ timeout: 180000 }); // first compile is slow
  await tall(page, "catalogue-desktop-light");
  console.log("axe catalogue:", await axeOf(page));
  // … click through, shot(), axeOf() …
  console.log("errors:", errors.join("\n") || "none");
  await ctx.close();
}
await browser.close();
```

**Selector tips:**

- Scope to the dialog: `page.getByRole("dialog").getByLabel(…)`. A page search box and a dialog field often share a label, which gives a strict-mode violation.
- Base UI checkboxes: use `getByRole("checkbox", { name })`, not `getByLabel`, which also matches the hidden input.

### 4.10 Tests

Both kinds live beside the code, and every top-level `describe` starts with the Data ID.

- **API tests** (`api/<feature>.test.ts`) call the real API functions against the MSW mock.
  - Set the role with `writeMockRole(role)`. In `afterEach`, call `resetMockDb()` and restore the default role.
  - Cover:
    - the happy path, filters and paging;
    - each 409 or 422 the backend names, through a `refusal(promise)` helper returning `{status, code}`;
    - a forbidden role getting 403.
- **UI tests** (`components/<feature>-ui.test.tsx`):
  - Render with `renderWithProviders(ui, { searchParams: "?tab=…" })` and include `<Toaster />` when asserting on toasts.
  - Sign in with `signInAs(role)`, which calls `writeMockRole(role)` and overrides `GET /auth/me` with `mockMeFor(role)`. Call it in **`beforeEach`**: setting the role only per test raced and gave 403s.
  - Mock `next/navigation`'s `useRouter` with `vi.mock(…)` when a component pushes routes.
  - Use `findByRole` or `findByText` for anything that depends on the session (`useCan`), since permissions load asynchronously.
  - Assert as a user would: roles, labels, visible text.
  - No `as` casts: to read an input's value, write a helper using `instanceof HTMLInputElement`.
- Unhandled requests fail a test, so every endpoint a screen calls needs a mock handler.
- `npm run verify` runs the whole suite (about 900 tests by now), and every one must pass.

### 4.11 The records: every PR keeps these current (AGENTS.md §11)

1. **Changelog:**
   - Run `npm run changelog:new -- --type feature|fix|docs --data-id ID [--data-id ID2] --title "…"`.
   - Set `author: Nakul Srivastava`; the generator writes "Claude".
   - Fill in every section: **Before, Now, Discussion, Files changed, Tests**. Copy the style of `changelog/entries/2026-10-11--feature--MSTR-004--…`: short bullets, behaviour rather than code, every state covered, decisions and their reasons, the mock's limits, the tests by file, and the by-hand walk.
   - Run `npm run changelog:build`, and never edit `CHANGELOG.md` by hand.
2. **`Docs/Plan.md` §9:**
   - Bump "Last updated" and add one sentence to the living paragraph.
   - Add a §9.1 row (area, Data IDs, endpoints).
   - Remove the feature from §9.3.
3. **`Docs/Tested-Features.md`:**
   - Add an "At a glance" row (module, story count, marks, `PR #109`).
   - Add a section of user stories with links to the screenshots.
   - Update "Not built yet".
   - Marks: 🧪 automated, 🌐 end to end, 👀 walked through, 🔌 checked on the real backend. **Never mark 🔌 without that check.**
4. **`docs/Backend-Tasks.md`:**
   - For anything you need from the backend, add a `BE-NNN` checklist line under a module heading, plus a details block (Status ⬜ Open, Asked, What, Why, Done when).
   - Before numbering, check the numbers used on every remote branch:
     ```bash
     for b in $(git branch -r | grep -v HEAD); do git show $b:docs/Backend-Tasks.md 2>/dev/null | grep -o "BE-0[0-9][0-9]"; done | sort -u
     ```
5. **Screenshots** in `Docs/screenshots/<module>/` (§4.9).
6. Once the PR exists, replace `PR #109` with the real number (`sed -i 's/PR #109/PR #95/g' Docs/Tested-Features.md`), then commit and push that.

### 4.12 Final checks, commit, push, PR

1. Run, from `Frontend/`: `npm run verify`, `npm run knip` (remove each unused export it lists), `npx prettier --check .` (or `--write` on your files), and `npm run build`. All must be clean.
2. **Commit:**
   - Use Conventional Commits with the Data ID as the scope: `feat(MSTR-004): products and prices — catalogue, GST by HSN code, price lists`. Use `fix(…)`, `docs(…)`, or `chore(…)` for merges.
   - Write a short body: what and why.
   - Add the attribution trailers (§2).
3. **Push:** `git push -u origin <branch>`. The pre-push hook takes minutes.
4. **Open the PR** with `mcp__github__create_pull_request`:
   - `base: integration`, or the lower branch for a stacked PR.
   - Follow `.github/pull_request_template.md`: What changed and why, Area, Before merging (checkboxes, saying CI is blocked and listing your local checks), How to check it (numbered click steps), and the attribution lines.
5. Put the PR number into the records and push again (§4.11, step 6).
6. **Report to the user:** a summary, what's left or risky, and "What I changed".

### 4.13 After the PR: conflicts and review

- `integration` moves fast: the backend merges several PRs a day, so open PRs go into conflict. Check with `gh api repos/polysil-company/polysil-crm/pulls/<n> --jq '.mergeable_state'` ("dirty" means a conflict).
- **To resolve one:**
  1. `git checkout <branch> && git merge --no-edit origin/integration`. **Merge, never rebase or force-push:** the user may have the branch checked out.
  2. Conflicts are nearly always "both sides added something" (two nav items, two mock tables, two handler groups, two doc sections). Keep both.
  3. For `CHANGELOG.md`, run `git checkout --theirs Frontend/CHANGELOG.md && npm run changelog:build` and never merge it by hand.
  4. Fix the records the merge made inconsistent: §9.3 rows, "Not built yet", the "At a glance" rows.
  5. Run `eslint --fix` on the merged code files (import order).
  6. Rerun verify, knip, prettier and build, then commit (`chore(ID): merge integration …`, listing what the conflicts were) and push.
- **Review comments:** fix the small ones and push. For larger ones, propose first. Reply on the thread, ending with the GitHub footer (§2).

---

## 5. How work was split into PRs, and stacking

- **One PR = one coherent capability a user can try end to end,** usually one Data ID group, with its API, mock, UI, tests and records. Examples:
  - #89 change password (AUTH-007);
  - #90 users and roles (ADMN-001…006);
  - #95 products and prices (MSTR-004…006).
- **Big modules are split into slices,** each a PR stacked on the one before:
  - Subsidy: #77 calculator (SUBS-002/003) → #78 applications (SUBS-004…008) → #79 reports (SUBS-009…011) → #86 masters and state schemes (SUBS-012…014).
  - Complaints were split the same way: the core list and workflow, then remedies, files, targets and export.
- **When to open the PR:** once the slice is complete. That means tests pass, the walk and screenshots are done, the records are written, and verify, knip, prettier and build are clean. No draft PRs, and no PRs with TODO-shaped holes.
- **Stacking:**
  - Branch the next slice from the previous slice's branch, and open its PR **against that branch**.
  - The PR body's **first line** says it is stacked and gives the merge order, for example: "Stacked on #78 (which is on #77). Merge order: #77 → #78 → #79."
  - When a lower PR merges, the next one must be **retargeted to `integration`** before it merges. GitHub only does this by itself if the merged branch was deleted. Otherwise its changes land on the lower branch and never reach `integration`.
  - Keep stacks short (four PRs at most). Merge `integration` into the bottom one when it conflicts, then merge each branch up the stack in turn.
- **Docs-only PRs** use a `docs/<slug>` branch. Examples: #87, the client demo guide (`Docs/Demo-Guide.md`), and this file.
- **Fix PRs** after a client or staging walk use one PR per walk, for example "Demo-walk fixes" (`fix(RPT-001)`). Each finding cites its walk ID (F-1, D-2, …).

---

## 6. Subagents

None were used for this build. The user's rule is to spawn subagents only when asked: each one starts cold and re-reads everything. All research (reading handovers, grepping the codebase) and all coding was done directly in the main session.

If the user asks for one, a read-only `Explore` agent is reasonable for a broad sweep, such as "find every place that renders a lead's score". Review whatever it returns yourself before acting.

---

## 7. Where things are (a map)

| What | Where |
| --- | --- |
| Contributor rules | `Frontend/AGENTS.md` |
| Design tokens and their meaning | `src/styles/tokens.css`, `Docs/Design-System.md` |
| Architecture, sessions and auth | `Docs/Frontend-Architecture.md` |
| Roles, modules, open client questions | `Docs/Frontend-Scope.md` (§10 questions) |
| Integration status | `Docs/Plan.md` §9 |
| Every user story and how it was tested | `Docs/Tested-Features.md` |
| Client demo script, click by click | `Docs/Demo-Guide.md` |
| Data IDs | `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` |
| API client, errors, idempotency | `src/lib/api/client.ts`, `errors.ts`, `error-messages.ts`; `src/hooks/use-idempotency-key.ts`, `use-async-action.ts` |
| Permissions | `src/lib/auth/permissions.ts`, `features/session/hooks/use-session.ts` (`useCan`) |
| Navigation | `src/components/layout/navigation.ts` |
| Mocks | `src/mocks/db.ts`, `data/`, `handlers/`, `handlers/index.ts`; `src/lib/dev/mock-settings.ts` |
| Test helpers | `src/test/render.tsx`, `src/mocks/node.ts`, `src/mocks/data/sessions.ts` (`mockMeFor`) |
| Backend contracts | `backend/docs/api/*.md`, `backend/docs/handover/*.md`, `backend/docs/architecture/RBAC.md` |
| Asks between frontend and backend | `docs/Backend-Tasks.md` |

---

## 8. Traps already hit (save yourself the hour)

**Components and types:**

- `Button` variants are `primary`, `outline`, `ghost`, `destructive` and `link`. There is no `default`.
- `exactOptionalPropertyTypes` is on, so you can't pass `undefined` to an optional prop. Spread it in conditionally, or leave it out.
- **Lint autofix rewrites `cond && x` into `cond ? x : null`** (no leaked renders). For a boolean prop such as `disabled`, that gives `boolean | null`, which tsc rejects. Compute a named boolean first: `const blocked = a && b;`, then `disabled={blocked}`.
- `EmptyState` needs `icon`. `useNow()` takes no argument and returns a number.
- There is no `focus-ring` utility. The global focus style covers buttons and links; use `focus-ring-inset` inside clipped containers.
- Base UI `Select` values are strings. For "none or every", use a sentinel such as `"every"` and map it back to `null`.

**Accessibility and copy:**

- An `opacity-60` avatar failed axe colour contrast. Don't fade text-bearing elements.
- Never `.toLowerCase()` a sentence containing names or dates: it gave "gujarat · dealers" and "1 nov 2026". Write sentence-shaped helpers instead (`scopeInSentence`).
- In JSX text, write `'` as `&apos;`.

**APIs and dates:**

- An `effective_to` from the backend is **exclusive**: the first day without the thing. Show "last day = to − 1", and send last day + 1 (`shiftCalendarDay`).
- `PUT …/items`-style endpoints replace everything, so read all pages first, merge, then PUT. Never send just the page on screen.
- The five keyless `/auth` endpoints are listed in `KEYLESS_AUTH_PATHS` in `client.ts`. A new auth endpoint without an Idempotency-Key needs adding there.

**Environment and tooling:**

- A stale `.next/types` causes phantom route errors (§3).
- Don't `pkill -f` with a pattern that appears in your own command (§3).
- `pre-push` runs the whole test suite, so allow minutes.

**Tests:**

- No `as HTMLInputElement`: use an `instanceof` helper.
- A discriminated union body needs `Extract<Request, { user_type: "staff" }>`.

---

## 9. What is built (as of `ed010e1`)

Everything below is merged into `integration`. Each one has unit and UI tests and was walked through in the mock (👀). Sign-in and the lead list are also checked on the real backend (🔌).

| Area | Data IDs | PRs (main ones) |
| --- | --- | --- |
| Sign-in (email and password, partner WhatsApp code), session, refresh, sign-out, forced and voluntary password change | AUTH-001…007 | early PRs, #89 |
| App shell, nav with live badges, command menu, theme, mock role switcher | APP-* | early |
| Dashboard on the backend's contract | RPT-001 | #41 |
| Leads: list (cursor, filters, area drill-down, sort), create, page, history and notes, stage, reopen, assign, edit, delete, duplicates and merge, export | LEAD-001…012 | many, #42 |
| QR codes and the public enquiry page `/enquiry` | LEAD-013, LEAD-014 | #76 |
| Quotations: list, detail, PDF, builder with live pricing, send, discount approval, customer link `/q/{token}`, revise, delete | QUOT-001…012, MSTR-003 | #20s–#40s |
| Approvals inbox (orders, quotation discounts, complaint refunds), approval limits | APPR-001, APPR-002 | #35 and others |
| Sales orders: list, detail, from a quotation, direct orders, approval, dispatch, export; Dispatch queue | SO-001…005, DISP-001/002 | #34, #56 |
| Notifications bell, messages (1:1) | NOTIF-001/002, MSG-001…005 | #43 |
| Tasks, planner, minutes, All tasks and export | TASK-001…008 | #54, #55 |
| Complaints: list, raise, check, QC, remedies (refund or replacement), files, targets, export | CMPL-001…009 | #57, #58 |
| Subsidy: calculator, applications (stages, documents, PIMS sheet), reports, masters, state schemes | SUBS-002…014 | #77, #78, #79, #86 |
| Users and roles (people, accounts, leavers), offices | ADMN-001…006 | #90 |
| Products and prices: catalogue, HSN and GST, price lists | MSTR-004…006 | #95 |

**Open PRs at the time of writing:**

- #98 `portal-ratings` is a backend PR.
- #11 and #7 are the standing integration → staging → main PRs.

No frontend PR is open.

---

## 10. Everything left to build, in order

**How complete this list is.** §10 was checked two ways on 11 October 2026:

1. **Endpoint by endpoint.** Every endpoint in `backend/docs/api/*.md` (372) was compared with every endpoint the frontend's mock serves (178). Every call the frontend makes must be mocked, because an unhandled request fails a test, so the mock is a reliable list of what the frontend uses. **194 endpoints have no frontend yet.** The coverage table is in "The measured gap" below, the full list in §12, and the script to measure it again in §12.2.
2. **Field by field,** from the recent handovers. Built endpoints have also gained fields and filters the screens don't use yet. These are in P1 under "New fields on screens already built". The endpoint comparison can't see them, so read every new handover for this kind of change.


The client is going live on **leads, quotations and sales orders** first, so P0 is what that go-live needs. Within each tier, top first.

### P0: go-live fixes for leads, quotations and orders

These come from the 10 Oct staging walk: `backend/docs/handover/walk-fixes-10-oct.md` and `walk-fixes-10-oct-whatsapp-history-approvals.md`, section "Yours (frontend)". The backend side is done; each needs a frontend change. **Read both files first:** the item text below is a summary.

- [x] **F-1:** a dealer still sees the lead score, the duplicates box and the "Possible duplicates" button. Hide them for partner users. The API now sends `score: null` and empty `duplicates`.
- [x] **F-8:**
  - Route guards: a dealer can open `/approval-limits`, `/qr-codes` and `/dispatch` by URL. `GET /approvals/thresholds` is now 403 for non-staff.
  - The empty approval-limits text says "Ask the backend team to seed them"; change it to "No approval limits are set."
  - On `/qr-codes` a dealer sees his own codes read-only: hide New QR code, Edit and Switch off, since `POST`/`PATCH /lead-qr-codes` are 403 for dealers.
- [x] **F-9:** the channel-partner box holds "No channel partner" as editable text, so typing searches `q=No+channel+partnerBhavesh`. Make it a real placeholder.
- [x] **F-11:** show `approval.steps[].stalled` on the approval trail of orders, quotations and complaint refunds. The text is "No District Manager to decide. With the next manager up." The inbox already handles the row-level `stalled`; the per-step trail on detail pages does not.
- [x] **F-13:** the first click after a page loads is ignored on `/tasks`, `/leads`, the lead page and `/approvals`. On `/approvals`, the next Approve after a decision needed up to 4 clicks. Investigate likely causes: a focus trap or overlay from the page transition, or the command-menu listener.
- [x] **F-14:** "Preparing PDF" doesn't clear without a reload after Send. The poll must keep running when the tab isn't focused (TanStack `refetchIntervalInBackground: true` on that query).
- [x] **F-16:** timeline text.
  - Use the new numbers in the payloads (`loser_inquiry_no`, `survivor_inquiry_no`, `matches[].inquiry_no`, `other_inquiry_no`).
  - A draft has no number, so write "draft quotation v1".
  - Don't repeat "the customer · Quotation opened by the customer QT/…".
  - One line per discount decision.
- [x] **F-17:** access-denied pages show "REF TASK-001 · <uuid>". Drop the reference, and don't draw the page behind the message.
- [x] **F-19, copy:**
  - Dealer sign-in says the code comes "by SMS"; it comes on WhatsApp.
  - The enquiry form shows the QR code's internal label to the farmer.
  - It reads "Loading…" before a state is picked.
  - It should submit by itself on the 6th digit.
  - Other copy items are listed in the handover.
- [x] **F-19, menus:** a field officer has Assign on a lead, and QR codes, Dispatch queue and Complaint targets in the menu. Check against the role table (`backend/docs/architecture/RBAC.md`), and ask the user if unclear.
- [ ] **F-12:** files on a complaint can't be added after the QC verdict. Ask the user to confirm this is meant.
- [x] **F-20:** check by eye that the theme button's "Light" gives a light page.
- [x] **Leads, from `walk-fixes-10-oct.md` "Changed responses":** (all but the optional "Deleted leads" view)
  - Show `score` as a whole number (it is now `"28.00"`).
  - Leave deleted leads out of the lists (the backend does already). Optionally add a "Deleted leads" view with `deleted=true` for `leads.delete` holders.
  - Refetch open draft quotations after an assign changes the partner: they are re-priced at the new tier.
  - `land_hectares` on the lead forms (client sheet, #93 backend; see `dealer-recruitment-and-small-changes.md` "Five small changes").
- [ ] **The mock's product gap:** quotation pricing in the mock still uses the six `MOCK_PRODUCTS` (`src/mocks/data/quotations.ts`), so a product added in Products & prices doesn't price in the mock builder. This is optional, mock-only polish: make `POST /pricing/quote-lines` in the mock read `mockDb.products` and the in-force price list.

Ship these as one or two `fix(...)` PRs ("Go-live fixes from the 10 Oct walk"), each finding named.

**12 October:** done in PR #109 (changelog `2026-10-12--fix--APP-006--go-live-fixes-from-the-10-oct-walk.md`). F-19 menus were checked against RBAC.md and left as they are. Still open: F-12 and the menu questions wait on the user; the "Deleted leads" view and the mock's product gap are optional.

### P1: backend pick-ups waiting on the frontend

- [ ] **BE-021, done by the backend:** `GET /conversations/{id}`. The thread header should name the colleague after a reload or from a shared link (`features/messages`). Handover: `accounts-queue-order-names.md`.
- [ ] **BE-022, done by the backend: the Accounts queue** (nav "Accounts queue", ACCT-001, now "Soon").
  - `GET /orders?waiting_on=account_manager` (also on `/orders/stats` and `/orders/export`).
  - The badge comes from stats `waiting_on.account_manager`.
  - **Payments** (`payments-contract.md`): `GET`/`POST /payments`, `payments` on `GET /orders/{id}` (a Payments tab on the order), instalments, and the dealer ledger.
- [ ] **BE-023 and BE-024 are open on the backend.** When ticked:
  - BE-023: the subsidy card on a lead uses `GET /subsidy-applications?lead_id=`;
  - BE-024: the product form uses `GET /lookups/product-categories` and `/lookups/uoms` instead of reading categories and units from the catalogue (`listCatalogueFacets` in `features/products/api/products.api.ts`).
- [ ] **Subsidised orders and the rest of #94 and #96:**
  - `subsidised-orders-and-small-changes.md`: the "Subsidised" order type on the new-order screen and order page, the dealership enquiry type, GSTIN details lookup, and amending after a voided dispatch.
  - `subsidy-completion.md`: the farmer's share paying a subsidised order, the dispatch date on an application, new bell notifications, reopening a closed file, and Sprinkler areas between steps.
  - `subsidised-quotations.md`: check what is already covered in the quotation builder.

- [ ] **Missing pieces of modules that are otherwise built** (from the endpoint comparison; check each against its handover):
  - **Orders:**
    - `POST /orders/{id}/amend`: amend an approved order (`settings-amend-reopen-contract.md`; also "Amend after a voided dispatch" in `subsidised-orders-and-small-changes.md`);
    - `PUT /orders/{id}/subsidy`: subsidised orders;
    - `GET /orders/{id}/schemes`: schemes applied to an order;
    - `GET /orders/stats`: counts, also used for the Accounts queue badge (BE-022);
    - `GET /orders/{id}/dispatches`: the order page reads dispatches from the order today; check whether this adds anything.
  - **Quotations:** `PUT /quotations/{id}/subsidy` and `GET /quotations/{id}/subsidy/calculation`, the subsidised quotation (`subsidised-quotations.md`).
  - **Complaints:** `POST /complaints/{id}/reopen` (`settings-amend-reopen-contract.md`).
  - **Subsidy applications:** `POST /subsidy-applications/{id}/reopen`, reopening a closed file (`subsidy-completion.md` §4), and `GET /subsidy-document-types`.
  - **Messages:** `GET /conversations/{id}` (BE-021), plus group chats: `POST /conversations/groups`, `PATCH /conversations/{id}`, and the members endpoints (`group-chat.md`).
  - **Tasks:** `GET /minutes/{id}`, one set of minutes on its own page.
  - **Approvals:** `GET /approvals/{request_id}`, one approval request on its own; check whether a deep link needs it.
  - **Lookups admin:** create and edit for complaint types, crops, lead sources, lost reasons, meeting types and MIS systems, plus `GET/PATCH /lookups/scoring` for lead scoring. The forms read these lists already, but nothing edits them. This is the "Masters" admin screen.
  - **Org units:** only the list is used (by the users screens). Create, read, edit, close and reopen offices are missing.
- [ ] **New fields on screens already built** (the endpoint comparison can't see these):
  - **Dashboard** (`GET /dashboard/overview`): `area_by_system: [{system, name, leads, hectares}]`, and `targets_by_month: [{month, target, achieved}]` (6 months, null without a targets permission). Two new charts (`dealer-recruitment-and-small-changes.md`, "Five small changes").
  - **Order list filters:** `territory_id` (a comma list; a state selects its districts) and `owner_org_unit_id` on `GET /orders`, `/orders/stats` and `/orders/export`, as the lead list already has.
  - **Land in hectares:** leads take and return `land_hectares` (`land_acres` still works). Ask for hectares on the lead forms and show it on the lead page.
  - **Lead score** as a whole number, and the other P0 items above.
  - **Dormant leads and "assign moves the office":** `lead-small-gaps-contract.md`. Dormant is already in the lead schemas; check the "Screens" section of that file against what is on screen.
  - **List exports:** `list-exports.md`. Leads, quotations and orders have export buttons; check the rest of the lists it names.

### The measured gap: built endpoints per backend module

| Module (backend/docs/api) | Built / total | Missing |
| --- | --- | --- |
| `approvals` | 4 / 5 | 1 |
| `assistant` | 0 / 2 | 2 |
| `auth` | 7 / 7 | 0 |
| `campaigns` | 0 / 5 | 5 |
| `complaints` | 21 / 22 | 1 |
| `customers` | 0 / 4 | 4 |
| `dashboard` | 1 / 1 | 0 |
| `dealer-applications` | 0 / 17 | 17 |
| `dealer-commission` | 0 / 12 | 12 |
| `dispatch` | 2 / 2 | 0 |
| `documents` | 0 / 6 | 6 |
| `holidays` | 0 / 3 | 3 |
| `leads` | 20 / 20 | 0 |
| `lookups` | 9 / 23 | 14 |
| `marketing-material` | 0 / 11 | 11 |
| `messages` | 6 / 12 | 6 |
| `notifications` | 2 / 2 | 0 |
| `orders` | 13 / 18 | 5 |
| `org-units` | 1 / 6 | 5 |
| `partners` | 0 / 7 | 7 |
| `payments` | 0 / 8 | 8 |
| `portal` | 0 / 6 | 6 |
| `pricing` | 8 / 8 | 0 |
| `products` | 8 / 8 | 0 |
| `public` | 6 / 6 | 0 |
| `quotations` | 14 / 16 | 2 |
| `ratings` | 0 / 4 | 4 |
| `reports` | 0 / 9 | 9 |
| `rewards` | 0 / 19 | 19 |
| `schemes` | 0 / 6 | 6 |
| `seller-gstins` | 0 / 3 | 3 |
| `settings` | 0 / 2 | 2 |
| `stock` | 0 / 7 | 7 |
| `subsidy` | 4 / 4 | 0 |
| `subsidy-applications` | 13 / 15 | 2 |
| `subsidy-masters` | 4 / 4 | 0 |
| `subsidy-reports` | 6 / 6 | 0 |
| `subsidy-schemes` | 6 / 6 | 0 |
| `targets` | 0 / 3 | 3 |
| `tasks` | 13 / 14 | 1 |
| `territories` | 0 / 4 | 4 |
| `tracking` | 0 / 16 | 16 |
| `users` | 10 / 10 | 0 |
| `warranty` | 0 / 3 | 3 |

The modules at 0 are the P2 table below. A partly built module has its missing pieces listed in P1 above. All 194 endpoints are listed in §12.

### P2: modules the backend serves with no screens yet

Each has a handover in `backend/docs/handover/` and an API file in `backend/docs/api/`. Rough order of value to the client, after go-live:

| # | Module | Handover(s) | Nav item |
| --- | --- | --- | --- |
| 1 | **Channel partners admin:** partners list and detail, onboarding, credit limit | `dealer-credit-limit.md`, `backend/docs/api/partners.md` | Channel → Channel partners (CHNL-001, "Soon") |
| 2 | **Dealer recruitment:** staff screens, and the public applicant page `/dealer-apply/<token>` | `dealer-recruitment-and-small-changes.md` | Channel |
| 3 | **Admin masters:** offices (org units), territories, the admin lookups (lead sources, crops, lost reasons, meeting and complaint types, lead scoring), company settings | `backend/docs/api/org-units.md`, `territories.md`, `lookups.md`, `settings-amend-reopen-contract.md` | Admin → Masters (MSTR-001, "Soon") |
| 4 | **Amend an approved order; reopen a complaint** | `settings-amend-reopen-contract.md` | — |
| 5 | **Reports, and the 360° lead view** | `reports-contract.md`, `list-exports.md`, `when-a-sale-counts.md` | Admin → Reports (RPT-002, "Soon") |
| 6 | **Targets and achievement** | `targets-contract.md` | — |
| 7 | **Schemes and promotions** | `schemes-contract.md` | Channel → Schemes (SCHM-001, "Soon") |
| 8 | **Reward points; dealer commission and TOD** | `rewards-contract.md`, `dealer-commission-contract.md` | — |
| 9 | **Marketing material ordering; campaigns** | `marketing-material-contract.md`, `campaigns.md` | Channel → Marketing (MKT-001, "Soon") |
| 10 | **Stock:** warehouses, availability on the order form, the stock list | `stock-contract.md` | — |
| 11 | **Documents on records** (built in PR #113: lead, quotation, order, dispatch); the replacement order's approvers (nothing to build) | `documents-and-replacement-chain.md` | — |
| 12 | **Warranty tracking** | `warranty.md` | — |
| 13 | **Group chats** | `group-chat.md` | Messages |
| 14 | **Export and sample orders**, with the seller GSTINs and their LUTs (`/seller-gstins`) | `export-sample-orders-contract.md`, `backend/docs/api/seller-gstins.md` | — |
| 15 | **Dealer tasks** (tasks for partner users) | `dealer-tasks-contract.md` | — |
| 16 | **Complaint holidays and escalation** (admin) | `complaint-holidays-escalation.md` | — |
| 17 | **Customer record** | `customer-record.md` | — |
| 18 | **Ratings; consumer portal** | `ratings-contract.md`, `consumer-portal.md` (backend PR #98 open) | — |
| 19 | **Field tracking map screens** (the Android app is separate) | `field-tracking-contract.md` | — |
| 20 | **In-app assistant** | `in-app-assistant.md`, `docs/PendingFeatures.md` §4 | — |
| 21 | **A consolidated order** from several quotations of one dealer | `orders-api-contract.md` (`POST /orders` with several `quotation_ids`) | — |
| 22 | **Complaint types admin** | `complaints-contract.md` | goes with Masters |

**The dealer portal:** most screens above already scope by role through the backend. After P0's route guards, walk every screen as `dealer`, `distributor` and `sub_dealer` (partner sign-in with the mock code in `Docs/Tested-Features.md`) and fix whatever leaks or breaks. That covers `docs/PendingFeatures.md` §1 item 9.

**Beyond the web app** (`docs/PendingFeatures.md` §2–§4): the field mobile app, the Polysil website, and the in-app help assistant. These are separate projects; plan them with the user first.

**Before going live on staging:**

- Run the `Docs/Live-Test-Plan.md` checklist against the staging backend.
- Mark 🔌 in Tested-Features only for what was really checked there.
- Credentials come from the user, never from a file. Never send WhatsApp messages to real customers.

---

## 11. A first message for the next session

Paste this to start:

> You are continuing the Polysil CRM web frontend in `polysil-company/polysil-crm` (`Frontend/`). First read `Frontend/AGENTS.md`, then `Frontend/Docs/Frontend-Handover.md` end to end, and follow its process exactly: branch from `origin/integration`, mocks first, a browser walk with screenshots and axe, tests, records, then verify, knip, prettier and build, then a PR to `integration`. Check `git log origin/integration` and `docs/Backend-Tasks.md` for anything newer than the handover's date. Then start on §10 P0, the go-live fixes from the 10 Oct walk, as one `fix` PR. Follow the user's rules in §2.

---

## 12. Appendix: every backend endpoint without a frontend (11 October 2026)

### 12.1 The list

194 endpoints, grouped by `backend/docs/api` module.

**`approvals (1)`**

- `GET /approvals/{request_id}`

**`assistant (2)`**

- `GET /assistant`
- `GET /assistant/actions`

**`campaigns (5)`**

- `GET /campaigns`
- `POST /campaigns`
- `DELETE /campaigns/{campaign_id}`
- `GET /campaigns/{campaign_id}`
- `PATCH /campaigns/{campaign_id}`

**`complaints (1)`**

- `POST /complaints/{complaint_id}/reopen`

**`customers (4)`**

- `GET /customers`
- `GET /customers/{customer_id}`
- `PATCH /customers/{customer_id}`
- `GET /customers/{customer_id}/timeline`

**`dealer-applications (17)`**

- `GET /dealer-applications`
- `POST /dealer-applications`
- `GET /dealer-applications/{app_id}`
- `PATCH /dealer-applications/{app_id}`
- `POST /dealer-applications/{app_id}/decision`
- `POST /dealer-applications/{app_id}/link`
- `POST /dealer-applications/{app_id}/submit`
- `POST /dealer-applications/{app_id}/withdraw`
- `GET /gstin/{gstin}`
- `GET /public/dealer-apply/{token}`
- `PATCH /public/dealer-apply/{token}`
- `POST /public/dealer-apply/{token}/documents`
- `DELETE /public/dealer-apply/{token}/documents/{doc_id}`
- `GET /public/dealer-apply/{token}/gstin/{gstin}`
- `POST /public/dealer-apply/{token}/submit`
- `POST /public/dealer-apply/{token}/verify`
- `POST /public/dealer-apply/{token}/verify/check`

**`dealer-commission (12)`**

- `GET /commission-rates`
- `POST /commission-rates`
- `GET /dealer-commissions`
- `GET /dealer-commissions/export`
- `GET /dealer-commissions/{commission_id}`
- `POST /dealer-commissions/{commission_id}/approve`
- `POST /dealer-commissions/{commission_id}/cancel`
- `POST /dealer-commissions/{commission_id}/pay`
- `POST /dealer-commissions/{commission_id}/return`
- `GET /subsidy-applications/{app_id}/commission`
- `POST /subsidy-applications/{app_id}/commission`
- `GET /subsidy-applications/{app_id}/commission/preview`

**`documents (6)`**

- `GET /documents`
- `POST /documents`
- `GET /documents/types`
- `DELETE /documents/{document_id}`
- `GET /documents/{document_id}/link`
- `GET /leads/{lead_id}/documents`

**`holidays (3)`**

- `GET /holidays`
- `POST /holidays`
- `DELETE /holidays/{day}`

**`lookups (14)`**

- `POST /lookups/complaint-types`
- `PATCH /lookups/complaint-types/{item_id}`
- `POST /lookups/crops`
- `PATCH /lookups/crops/{item_id}`
- `POST /lookups/lead-sources`
- `PATCH /lookups/lead-sources/{item_id}`
- `POST /lookups/lost-reasons`
- `PATCH /lookups/lost-reasons/{item_id}`
- `POST /lookups/meeting-types`
- `PATCH /lookups/meeting-types/{item_id}`
- `POST /lookups/mis-systems`
- `PATCH /lookups/mis-systems/{item_id}`
- `GET /lookups/scoring`
- `PATCH /lookups/scoring`

**`marketing-material (11)`**

- `GET /marketing-materials`
- `POST /marketing-materials`
- `PATCH /marketing-materials/{material_id}`
- `GET /marketing-orders`
- `POST /marketing-orders`
- `GET /marketing-orders/export`
- `GET /marketing-orders/{order_id}`
- `POST /marketing-orders/{order_id}/approve`
- `POST /marketing-orders/{order_id}/cancel`
- `POST /marketing-orders/{order_id}/dispatch`
- `POST /marketing-orders/{order_id}/reject`

**`messages (6)`**

- `POST /conversations/groups`
- `GET /conversations/{conversation_id}`
- `PATCH /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/members`
- `POST /conversations/{conversation_id}/members`
- `DELETE /conversations/{conversation_id}/members/{user_id}`

**`orders (5)`**

- `GET /orders/stats`
- `POST /orders/{order_id}/amend`
- `GET /orders/{order_id}/dispatches`
- `GET /orders/{order_id}/schemes`
- `PUT /orders/{order_id}/subsidy`

**`org-units (5)`**

- `POST /org-units`
- `GET /org-units/{item_id}`
- `PATCH /org-units/{item_id}`
- `POST /org-units/{item_id}/close`
- `POST /org-units/{item_id}/reopen`

**`partners (7)`**

- `GET /partners`
- `POST /partners`
- `GET /partners/export`
- `GET /partners/{item_id}`
- `PATCH /partners/{item_id}`
- `POST /partners/{item_id}/close`
- `POST /partners/{item_id}/reopen`

**`payments (8)`**

- `PUT /orders/{order_id}/payment-schedule`
- `GET /partners/{partner_id}/credit`
- `GET /partners/{partner_id}/ledger`
- `GET /payments`
- `POST /payments`
- `GET /payments/{payment_id}`
- `POST /payments/{payment_id}/allocations`
- `POST /payments/{payment_id}/void`

**`portal (6)`**

- `GET /portal/complaints`
- `GET /portal/enquiries`
- `GET /portal/me`
- `PATCH /portal/me`
- `GET /portal/orders`
- `GET /portal/quotations`

**`quotations (2)`**

- `PUT /quotations/{quotation_id}/subsidy`
- `GET /quotations/{quotation_id}/subsidy/calculation`

**`ratings (4)`**

- `GET /partners/{partner_id}/dealer-rating`
- `GET /ratings`
- `POST /ratings`
- `GET /ratings/summary`

**`reports (9)`**

- `GET /leads/{lead_id}/360`
- `GET /reports/campaign-performance`
- `GET /reports/complaints`
- `GET /reports/dealer-performance`
- `GET /reports/follow-ups`
- `GET /reports/lead-conversion`
- `GET /reports/lost-leads`
- `GET /reports/salesperson-performance`
- `GET /reports/territory-performance`

**`rewards (19)`**

- `GET /gifts`
- `POST /gifts`
- `PATCH /gifts/{gift_id}`
- `DELETE /orders/{order_id}/reward-redemption`
- `POST /orders/{order_id}/reward-redemption`
- `GET /reward-rules`
- `POST /reward-rules`
- `GET /reward-rules/{rule_id}`
- `PATCH /reward-rules/{rule_id}`
- `GET /reward-settings`
- `PUT /reward-settings`
- `POST /rewards/adjustments`
- `GET /rewards/balance`
- `GET /rewards/gift-redemptions`
- `POST /rewards/gift-redemptions`
- `POST /rewards/gift-redemptions/{rid}/fulfil`
- `POST /rewards/gift-redemptions/{rid}/reject`
- `POST /rewards/gift-redemptions/{rid}/withdraw`
- `GET /rewards/ledger`

**`schemes (6)`**

- `GET /scheme-entitlements`
- `GET /schemes`
- `POST /schemes`
- `GET /schemes/{scheme_id}`
- `PATCH /schemes/{scheme_id}`
- `GET /schemes/{scheme_id}/standing`

**`seller-gstins (3)`**

- `GET /seller-gstins`
- `POST /seller-gstins/{gstin_id}/luts`
- `DELETE /seller-gstins/{gstin_id}/luts/{lut_id}`

**`settings (2)`**

- `GET /settings`
- `PATCH /settings`

**`stock (7)`**

- `GET /stock`
- `GET /stock/availability`
- `GET /stock/movements`
- `POST /stock/movements`
- `GET /warehouses`
- `POST /warehouses`
- `PATCH /warehouses/{warehouse_id}`

**`subsidy-applications (2)`**

- `POST /subsidy-applications/{app_id}/reopen`
- `GET /subsidy-document-types`

**`targets (3)`**

- `GET /targets`
- `PUT /targets`
- `GET /targets/achievement`

**`tasks (1)`**

- `GET /minutes/{minutes_id}`

**`territories (4)`**

- `GET /territories`
- `POST /territories`
- `GET /territories/{item_id}`
- `PATCH /territories/{item_id}`

**`tracking (16)`**

- `POST /locations/batch`
- `GET /me/tracking-config`
- `POST /tracking/consent`
- `POST /tracking/duty/end`
- `POST /tracking/duty/start`
- `GET /tracking/policy`
- `PUT /tracking/policy`
- `GET /tracking/team/latest`
- `GET /tracking/users/{user_id}/route`
- `GET /tracking/view-log`
- `GET /visits`
- `POST /visits`
- `GET /visits/{visit_id}`
- `POST /visits/{visit_id}/check-out`
- `POST /visits/{visit_id}/photos`
- `GET /visits/{visit_id}/photos/{photo_id}`

**`warranty (3)`**

- `GET /orders/{order_id}/warranty`
- `GET /warranty-terms`
- `POST /warranty-terms`

### 12.2 Measure it again

The gap changes every time either side merges. To measure it again, run these from the repository root.

**Step 1: dump the frontend's mocked endpoints.** This is a scratch script: don't commit it. Its type cast is only there to read MSW's internal `info`.

```bash
cd Frontend
cat > src/__list-handlers.ts <<'TS'
import { handlers } from "@/mocks/handlers";
for (const h of handlers) {
  const info = (h as unknown as { info: { method?: unknown; path?: unknown } }).info;
  console.log(`${String(info.method)} ${String(info.path)}`);
}
TS
NEXT_PUBLIC_API_MOCKING=enabled NEXT_PUBLIC_APP_ENV=development npx tsx src/__list-handlers.ts > /tmp/fe-endpoints.txt
rm src/__list-handlers.ts
cd ..
```

**Step 2: compare with the backend's generated docs.**

```python
# python3 gap.py
import re, glob, os
def norm(p):
    p = re.sub(r"^.*?/api/v1", "", p.split("?")[0])
    p = re.sub(r"\{[^}]+\}", ":x", p); p = re.sub(r":[A-Za-z_]+", ":x", p)
    return p.rstrip("/")
fe = {(m, norm(p)) for m, p in (l.split() for l in open("/tmp/fe-endpoints.txt") if len(l.split()) == 2)}
for f in sorted(glob.glob("backend/docs/api/*.md")):
    if f.endswith("README.md"): continue
    for m in re.finditer(r"^## `(GET|POST|PUT|PATCH|DELETE) /api/v1(\S*)`", open(f).read(), re.M):
        if (m.group(1), norm(m.group(2))) not in fe:
            print(os.path.basename(f)[:-3], m.group(1), m.group(2))
```

A mocked endpoint isn't proof that a screen uses it. The reverse holds, though: an endpoint missing from the mock is certainly unused by the frontend.
