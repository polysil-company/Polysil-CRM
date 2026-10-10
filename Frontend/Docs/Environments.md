# Environments

Three environments. Code moves only forward: **feature → staging → production**.

| | Feature branch | Integration (staging) | Production |
|---|---|---|---|
| Purpose | Build and review one change in isolation | Frontend and backend tested **together** | Real users |
| Branch | `feature/<DATA-ID>-<slug>`, `fix/<DATA-ID>-<slug>` | `staging` | `main` |
| Deploy | Preview deployment per pull request | Automatic on merge to `staging` | Tagged release from `main` |
| API | **Mock backend (MSW)** — no backend needed | Backend **staging** API with the shared seed data | Backend production API |
| `NEXT_PUBLIC_APP_ENV` | `feature` | `staging` | `production` |
| `NEXT_PUBLIC_API_MOCKING` | `enabled` | `disabled` (build fails if enabled) | `disabled` (build fails if enabled) |
| `LOG_LEVEL` default | `debug` | `info` | `warn` |
| Who checks | Author + reviewer, Storybook, preview URL | Frontend + backend developer, then the client | — |
| Exit gate | CI green, review approved, changelog entry | Integration checklist passed (below) | — |

Local development behaves like a feature branch (`NEXT_PUBLIC_APP_ENV=development`, mocks on) —
or runs against the backend's shared dev API, [below](#the-dev-api).

---

## Variables

Copy [`.env.example`](../.env.example) to `.env.local`. Real values for deployed environments live
in the hosting platform — never in the repository.

| Variable | When it is read | Rules |
|---|---|---|
| `NEXT_PUBLIC_APP_ENV` | **Build time** (inlined) | `development` · `feature` · `staging` · `production` |
| `NEXT_PUBLIC_API_BASE_URL` | Build time | The API as the browser sees it. Default and recommended: `/api/v1` (same origin). Required in staging and production |
| `API_PROXY_TARGET` | Dev-server start and **build time** (server only) | The backend origin `/api/v1` is rewritten to, e.g. `http://127.0.0.1:8000`. Default in development; required in staging and production |
| `NEXT_PUBLIC_API_MOCKING` | Build time | `enabled` · `partial` · `disabled`. `partial` mocks only what the backend lacks. Anything but `disabled` is forbidden in staging and production |
| `NEXT_PUBLIC_RELEASE` | Build time | Release identifier (git SHA) — shown in logs and error references |
| `LOG_LEVEL` | **Runtime** | `debug` · `info` · `warn` · `error` · `silent`. See [Logging.md](Logging.md) |

**`NEXT_PUBLIC_*` values are baked into the JavaScript at build time.** Each environment therefore
needs its own build; you cannot promote one build artefact from staging to production by changing
variables. `LOG_LEVEL` is deliberately not `NEXT_PUBLIC_`, so it can change without a rebuild.

Validation lives in [`src/lib/env/client.ts`](../src/lib/env/client.ts): an invalid combination
fails `next build` with a clear message, so a misconfigured deploy never ships.

---

## The dev API

The backend team runs a shared development API with real data at
`https://polysil-api.pranayx.tech` — interactive docs at `/docs`, the contract at `/openapi.json`,
and `/health`. The backend keeps it on the latest `integration` (BE-012), so it serves every
module the frontend calls: sign-in, leads, lookups, quotations, approvals, orders and dispatch,
the dashboard, notifications and messages. Check `/openapi.json` when an endpoint seems missing:
a backend change reaches it only after it merges into `integration`.

To build against it, put these in `.env.local` and restart `npm run dev`:

```bash
API_PROXY_TARGET=https://polysil-api.pranayx.tech
NEXT_PUBLIC_API_MOCKING=partial
```

- **`partial` mocking** answers only the endpoints the backend lacks — `unbuiltHandlers` in
  [`src/mocks/handlers/index.ts`](../src/mocks/handlers/index.ts). Today that list is empty:
  every screen is connected, so `partial` sends every request to the dev API, like `disabled`,
  while keeping the mock tools in the account menu. A module built before its endpoints exist
  goes on that list until its screens are connected.
- **What leads cannot show yet.** The dev API records no follow-up date on a lead: follow-ups are
  tasks (BE-002), so that column reads "—" until the tasks module is built.
- **Sign in with a real account.** The accounts and their roles are listed in the backend's
  `docs/handover/dev-api-access.md`. The password comes from the backend team and never goes in a
  file. Roles see different data by design: a field officer's short list is not a bug.
- **Through the proxy, so no CORS.** The browser calls `/api/v1` on its own origin, and the refresh
  cookie is `SameSite=Lax` and first-party. A preview deployment works the same way, so it does not
  need registering with the backend.
- **Limits that look like bugs:** five failed sign-ins in fifteen minutes lock that email for
  fifteen; a mobile number may request three codes per fifteen minutes and ten a day.
- **The data is shared and disposable.** Tell the backend team before anything that would take a
  while to redo, and never restart anything on the box — it hosts other services.
- **Tests always use the full mock backend.** `vitest.config.mts` and `playwright.config.ts` pin
  `NEXT_PUBLIC_API_MOCKING=enabled`, whatever `.env.local` says. The one exception: Playwright
  reuses a dev server that is already running, so stop a dev-API `npm run dev` before
  `npm run test:e2e`.

---

## Integration checklist — before a feature leaves staging

- [ ] The Data ID status is `integrated` in `registry.ts`.
- [ ] Every screen of the feature works against the staging API with the shared seed data.
- [ ] No `CONTRACT_VIOLATION` in the browser console across the flows. If one appears, the schema or
      the backend is wrong — decide which with the backend developer and fix it at the source.
- [ ] Error paths checked against the real backend: 401, 403, 404, 422 field errors, 5xx.
- [ ] The backend logs show `x-request-id` and `x-data-id` for the feature's requests.
- [ ] Mock handlers updated to match the real contract (they stay useful for tests and previews).
- [ ] Changelog entry updated with anything learned during integration.

---

## Backend requirements for staging and production

- **Same origin, decided with the auth design (AUTH-001).** The browser calls `/api/v1` on the app's
  own origin, and `next.config.ts` rewrites it to `API_PROXY_TARGET`. The backend sends no CORS
  headers and scopes its httpOnly refresh cookie to `/api/v1/auth`, so a cross-origin API would lose
  the session. Keep `NEXT_PUBLIC_API_BASE_URL=/api/v1`.
- The backend must accept `x-request-id`, `x-data-id`, `x-client` and `idempotency-key`, and trust one
  proxy hop (`trusted_proxy_hops`) so rate limits see the visitor's address, not the app server's.
- Rewrites are resolved at build time: a staging build and a production build each need their own
  `API_PROXY_TARGET`.
- To run the app against a local backend: start the backend on port 8000, then set
  `NEXT_PUBLIC_API_MOCKING=disabled` in `.env.local` and restart `npm run dev`.

---

## Not decided yet

| Item | Owner |
|---|---|
| Hosting: VPS with Dokploy alongside the backend, or Vercel | Loopify + backend developer |
| Staging URL and seed data refresh | Backend developer |
| Error monitoring (Sentry / GlitchTip) | Loopify |
