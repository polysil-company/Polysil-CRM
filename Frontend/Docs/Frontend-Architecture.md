# Frontend architecture — Polysil CRM

**Version:** 1.0 · **Date:** 2026-09-14 · **Owner:** Loopify (frontend)
**Rules:** [AGENTS.md](../AGENTS.md) · **Design:** [Design-System.md](Design-System.md) ·
**Tracing:** [Data-IDs.md](Data-IDs.md), [Logging.md](Logging.md) · **Deploys:** [Environments.md](Environments.md)

How the web app is put together and how to extend it. AGENTS.md states the rules; this document
explains them and gives the recipes.

---

## 1. Stack

Versions are pinned exactly (`save-exact`, `engine-strict`). Upgrades happen in their own PR with a
`chore` changelog entry.

| Concern | Choice | Version | Why |
|---|---|---|---|
| Framework | Next.js, App Router | 16.3.5 | One codebase for the app and the future public site; streaming, route-level loading and error files |
| UI runtime | React | 19.3.0 | Stable `<ViewTransition>`, React Compiler |
| Language | TypeScript, strict | 6.0.3 | typescript-eslint supports < 6.1; TypeScript 7 (native) has no JS API for tooling yet |
| Styling | Tailwind CSS | 4.3.3 | Design tokens become utilities through `@theme` |
| Primitives | shadcn/ui on Base UI | CLI 4.21 · @base-ui/react 1.8.0 | We own the component code; accessible headless parts |
| Icons | Hugeicons (free) | 4.3.3 | Requested icon set |
| Server state | TanStack Query | 5.102.8 | Caching, deduplication, retries, invalidation |
| Tables | TanStack Table | 9.2.4 | Headless; explicit feature registration |
| URL state | nuqs | 2.10.1 | Filters, sorting, pages and dialogs live in the URL |
| Forms | React Hook Form + Zod | 7.88.0 · 4.6.5 | Same schema validates input and shapes the request |
| Motion | CSS transitions + Motion | 13.2.0 | CSS first; Motion for layout, presence, springs |
| Toasts, command menu | Sonner, cmdk | 2.0.8 · 1.1.1 | |
| Mock backend | MSW | 2.15.0 | Full UI before any endpoint exists; same handlers in tests |
| Unit tests | Vitest + Testing Library + jsdom | 4.1.11 · 16.3.3 · 29.1.1 | Vitest 5 is not yet supported by Storybook's Vitest addon |
| Component preview | Storybook (nextjs-vite) + a11y + themes | 10.6.0 | Isolated preview and tweaking of every component |
| End-to-end | Playwright + axe | 1.63.0 · 4.13.0 | Smoke and accessibility across real browsers |
| Lint | ESLint 9 + typescript-eslint + next + jsx-a11y + better-tailwindcss + TanStack Query + Storybook + Vitest | 9.39.5 | ESLint 10 is blocked by the React, import and jsx-a11y plugins' peer ranges |
| Format | Prettier + Tailwind class sorting | 3.9.6 | |
| Hooks | husky + lint-staged + commitlint | 9.1 · 17.5 · 21.2 | |
| Dead code | knip | 6.35.1 | |

Runtime: Node.js ≥ 24.13, npm 11 (`.nvmrc`).

---

## 2. Folder structure and layers

```
src/
├── app/                        Routes only: layouts, pages, loading, error, not-found
│   ├── (app)/                  Signed-in application inside <AppShell>
│   │   ├── dashboard/
│   │   └── (sales)/            Leads · Quotations · Sales orders share a header and tabs
│   ├── fonts.ts
│   ├── globals.css             Entry point — imports Tailwind and tokens; no styles
│   └── layout.tsx              <html>, theme script, providers
├── components/
│   ├── ui/                     Primitives (shadcn/Base UI, restyled)
│   ├── patterns/               Domain-free building blocks (DataTable, QueryView, StatCard …)
│   ├── layout/                 App shell, sidebar, header, navigation config, command menu
│   └── providers/              Client providers, mock gate
├── features/<feature>/
│   ├── api/                    *.schemas.ts · *.api.ts · *.queries.ts · *.mutations.ts
│   ├── components/
│   ├── hooks/
│   └── lib/                    Labels, table layouts, pure helpers
├── hooks/                      Generic hooks (no business knowledge)
├── lib/                        Foundation: api, logger, env, data-ids, format, auth, theme, motion, query, dev
├── mocks/                      MSW handlers and seeded data
├── styles/tokens.css           The design system
├── test/                       Test helpers
└── proxy.ts                    Runs before page requests (log-level cookie; auth later)
```

**Import rules — enforced by lint:**

| Layer | May import | Must not import |
|---|---|---|
| `lib/` | `lib/` | components, features, hooks, app, mocks |
| `hooks/` | `lib/` | components, features, app, mocks |
| `components/ui` | `lib/`, `hooks/` | patterns, layout, providers, features, app, mocks |
| `components/patterns` | `ui/`, `lib/`, `hooks/` | layout, providers, features, app, mocks |
| `components/layout` | everything above, `features/` | providers, app, mocks |
| `features/` | components (not layout/providers), `lib/`, `hooks/`, other features' `api/` and `lib/` | app, mocks |
| `mocks/` | features' schemas, `lib/` | components, app, hooks |
| `app/` | everything | mocks |

Other import rules: no `../` imports (use `@/`); icons only through `<Icon>`; `cn()` instead of
`clsx`/`tailwind-merge`; Motion from `motion/react`; no `next-themes`, no `next/router`; named
exports everywhere except route files, configs and stories.

---

## 3. Rendering model

- **Server Components by default.** Route files, layouts, `PageHeader`, `EmptyState` render on the
  server. Interactive pieces are client islands (`"use client"`): tables, forms, menus, anything
  using a hook.
- **Values from a `"use client"` module cannot be called on the server.** Keep shared constants and
  style functions in plain modules — for example `button-variants.ts`, `lead-table-layout.ts`.
- **Every route segment that loads data has:**
  - `loading.tsx` — the page's skeleton, built from the same skeleton components the page uses
  - `error.tsx` — inherited from `(app)/error.tsx` (ErrorState + retry + log) unless it needs its own
  - `not-found.tsx` — where `notFound()` can happen (e.g. `leads/[leadId]`)
- **URL state needs a Suspense boundary.** Pages that read filters from the URL wrap those parts in
  `<Suspense fallback={<…Skeleton />}>`, otherwise prerendering fails.
- **Page transitions:** pages wrap content in `<PageTransition>`; links choose a direction with
  `transitionTypes`. See Design-System.md §8.

---

## 4. Data layer

```
Component ──useQuery(leadListQueryOptions(params))──▶ TanStack Query cache
                                                         │ miss / stale
                                                         ▼
                                   listLeads(params, signal)        features/leads/api/leads.api.ts
                                                         │
                                                         ▼
                                   apiRequest({ dataId, logger, fn, path, schema })   lib/api/client.ts
                                   · x-request-id + x-data-id headers
                                   · logs request / response / failure
                                   · validates the body with Zod → CONTRACT_VIOLATION on mismatch
                                   · throws ApiError only
                                                         │
                                                         ▼
                                   fetch ── MSW intercepts in development, previews and tests
```

**One file per concern in `features/<feature>/api/`:**

| File | Contains |
|---|---|
| `*.schemas.ts` | Zod contract: response shapes, request bodies, form schemas, enums, types |
| `*.api.ts` | One exported function per endpoint, each calling `apiRequest` with its Data ID |
| `*.queries.ts` | Query key factory + `queryOptions()` factories with `meta: { dataId }` |
| `*.mutations.ts` | `useMutation` hooks with their cache updates and invalidation |

**Rules:**

- `fetch` is only allowed in `lib/api` (lint). Every call has a Data ID, a logger and a response schema.
- Components never write query keys or query functions inline — they use the `queryOptions`
  factories (lint: `@tanstack/query/prefer-query-options`). One place per query to change caching.
- No data fetching in `useEffect`.
- Pass TanStack Query's `signal` to the API function so abandoned requests are cancelled.
- Lists use `placeholderData: keepPreviousData` — the previous page stays visible while the next loads.
- Mutations update or invalidate caches by key prefix (`leadKeys.lists()`), without awaiting refetches
  in `onSuccess`.

**Cache policy:**

| Data | `staleTime` | Reason |
|---|---|---|
| Default | 30 s | Returning to a screen within 30 s is instant and makes no request |
| Session (`GET /me`) | 5 min | Rarely changes during a visit |
| Counts, dashboard | 60 s | Slow-changing aggregates shown in navigation |

`gcTime` is 5 minutes. Window focus refetches stale queries.

**Retries:** network errors, timeouts, 408, 429 and 5xx retry up to twice with exponential backoff.
4xx and contract violations never retry — retrying cannot fix them. Mutations never retry automatically.

TODO(AUTH-001): once the auth mechanism is known, prefetch critical queries on the server and pass
them through `HydrationBoundary`, so first paint shows data instead of skeletons.

---

## 5. Every data view handles four states

`<QueryView>` requires `pending`, `empty` and `isEmpty`, and renders `ErrorState` by default:

```tsx
<QueryView
  query={useQuery(leadListQueryOptions(params))}
  pending={<LeadsTableSkeleton />}
  isEmpty={(data) => data.total === 0}
  empty={<EmptyState icon={UserAdd01Icon} title="No leads yet" description="…" />}
>
  {(data) => <DataTable … />}
</QueryView>
```

Edge cases to handle explicitly (the leads table is the reference):

- empty because nothing exists **vs** empty because filters match nothing (different copy and action)
- a page number beyond the last page (offer "Go to the first page")
- a refetch that fails while data is on screen (keep the data, show a retry notice)
- 404 on a detail page → `notFound()`
- 401 / 403 → user-facing copy from `toUserFacingError()`; TODO(AUTH-001) redirect to sign-in
- slow responses → skeleton first, then the refetch bar; never a blank screen

Use the mock scenarios (account menu → Data scenario) to see each state in the running app.

---

## 6. Forms

- **Two schemas:** the *form* schema describes what people type (strings) and transforms it; the
  *request* schema describes what the backend receives. Mocks validate requests with the request schema.
- `useForm<FormValues, unknown, Request>({ resolver: zodResolver(formSchema), mode: "onTouched" })`
  — errors appear after a field is left, then update while typing.
- Read errors with `useFormState({ control })`, not by destructuring `formState` or calling `watch`
  (React Compiler compatibility).
- Selects and custom inputs go through `<Controller>`.
- Submit with `useAsyncAction` + `<Button state>`: no double submits, visible progress, logged outcome.
- Server validation (422) returns `details.fields: { name: message }`; those messages land on the
  matching fields. Anything else shows an inline error with a copyable reference.
- Dialog open state lives in the URL (`?newLead=true`) so links and the command menu can open it.

---

## 7. Contracts and mocks

- The Zod schemas in `*.schemas.ts` **are** the contract until an OpenAPI spec exists. Agree them with
  the backend developer, then change them first when the contract changes.
- A response that breaks its schema throws `ApiError(kind: "contract")` and logs
  `CONTRACT_VIOLATION` with the failing paths — the fastest way to see that a backend change broke
  the frontend.
- Mock data is generated from a fixed seed and **parsed with the real schemas**, so mocks cannot drift.
- Handlers live in `src/mocks/handlers/<feature>.ts` and are registered in `handlers/index.ts`.
- Scenarios (`realistic`, `slow`, `empty`, `error`, `contract`) and a role switcher live in the account
  menu when mocking is on. `GET /me` ignores the error scenario so the menu stays usable.
- Tests use the same handlers through `msw/node`, and fail on any unhandled request.

TODO(OBS-002): generate schemas and the Data ID registry from the backend's OpenAPI spec when it exists.

---

## 8. Roles and permissions

- Roles and channel partner types: `src/lib/auth/roles.ts`. Permission matrix: `src/lib/auth/permissions.ts`.
- `useCan("leads:create")` and `can(role, permission)` hide what a role cannot use. **UI gating only** —
  the backend must enforce every permission.
- The navigation is data (`src/components/layout/navigation.ts`): each item declares its route,
  permission(s) and Data ID. Planned modules appear as "Soon" without links.
- TODO(AUTH-002): replace the placeholder matrix with the permission list returned by `GET /me`, and
  add route guards so a hidden page cannot be opened by URL.

---

## 9. React Compiler

- Enabled (`reactCompiler: true`). Do not add `useMemo`, `useCallback` or `React.memo` by hand.
- Lint runs the compiler's rules (`react-hooks/*`): purity, refs, set-state-in-effect, static components.
- `DataTable` opts out with `"use no memo"`: TanStack Table keeps stable row objects while state changes,
  which memoisation would treat as unchanged.
- Read the clock through `useNow()`, not `Date.now()` during render.

---

## 10. Adding a feature — the checklist

1. **Register Data IDs** in `src/lib/data-ids/registry.ts` (one per endpoint or action).
2. **Contract:** write the schemas in `features/<feature>/api/<feature>.schemas.ts`; agree them with
   the backend developer.
3. **Mocks:** seed data (parsed with the schemas) and handlers, including 404/422 paths.
4. **API functions** in `<feature>.api.ts` through `apiRequest`.
5. **Queries and mutations** in `<feature>.queries.ts` and `<feature>.mutations.ts`.
6. **Components** with `QueryView` (all states), skeletons that mirror the layout, patterns from
   `components/patterns` before inventing new ones.
7. **Routes:** `page.tsx` in `<PageTransition>` + `<PageContainer>`, `loading.tsx`, `not-found.tsx`
   where relevant.
8. **Navigation:** add or update the item in `navigation.ts` (route + permission).
9. **Tests:** API functions against MSW, component states, hooks. `describe("[DATA-ID] …")`.
10. **Stories** for any new pattern or primitive.
11. **Changelog entry** in `changelog/entries/`.
12. **`npm run verify`** — typecheck, lint, unit tests, changelog check.

---

## 11. Testing

| Layer | Tool | What to test | Runs |
|---|---|---|---|
| Pure logic (`lib/`, formatters, schemas, redaction) | Vitest | Inputs → outputs, edge cases | `npm test` (pre-push, CI) |
| API functions | Vitest + MSW | Success, each error kind, contract violation, headers | `npm test` |
| Hooks | Vitest + Testing Library | State transitions, timers | `npm test` |
| Components | Vitest + Testing Library | Every state, keyboard use, accessible names | `npm test` |
| Visual + accessibility | Storybook + axe (Chromium) | Every story renders without a11y violations | `npm run test:storybook` |
| Flows | Playwright + axe | Navigate, filter, create, detail, back | `npm run test:e2e` |

Top-level `describe` titles start with the Data ID. Query elements the way a user finds them
(`getByRole`, `getByLabelText`), not by test IDs.

---

## 12. Known gaps

| Gap | Tracking |
|---|---|
| Authentication, sign-out, route guards | AUTH-001, AUTH-002 |
| Server-side prefetch for first paint | AUTH-001 |
| Remote error and log collection | OBS-001 |
| Content-Security-Policy with nonce | OBS-002 |
| OpenAPI-generated schemas | OBS-002 |
| Row virtualisation for very large pages | Not needed at 25–100 rows per page |
| Offline support for field users (Next 16.3 `useOffline`) | Evaluate with the mobile scope |
