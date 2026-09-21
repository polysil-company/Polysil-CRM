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

Local development behaves like a feature branch (`NEXT_PUBLIC_APP_ENV=development`, mocks on).

---

## Variables

Copy [`.env.example`](../.env.example) to `.env.local`. Real values for deployed environments live
in the hosting platform — never in the repository.

| Variable | When it is read | Rules |
|---|---|---|
| `NEXT_PUBLIC_APP_ENV` | **Build time** (inlined) | `development` · `feature` · `staging` · `production` |
| `NEXT_PUBLIC_API_BASE_URL` | Build time | Absolute URL or same-origin path (`/api/v1`). Required in staging and production |
| `NEXT_PUBLIC_API_MOCKING` | Build time | `enabled` · `disabled`. Forbidden in staging and production |
| `NEXT_PUBLIC_RELEASE` | Build time | Release identifier (git SHA) — shown in logs and error references |
| `LOG_LEVEL` | **Runtime** | `debug` · `info` · `warn` · `error` · `silent`. See [Logging.md](Logging.md) |

**`NEXT_PUBLIC_*` values are baked into the JavaScript at build time.** Each environment therefore
needs its own build; you cannot promote one build artefact from staging to production by changing
variables. `LOG_LEVEL` is deliberately not `NEXT_PUBLIC_`, so it can change without a rebuild.

Validation lives in [`src/lib/env/client.ts`](../src/lib/env/client.ts): an invalid combination
fails `next build` with a clear message, so a misconfigured deploy never ships.

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

- CORS (if the API is on another origin): allow request headers `content-type`, `x-request-id`,
  `x-data-id`, `x-client`; expose `x-request-id`.
- Or proxy the API through the Next.js app (same origin) and set `NEXT_PUBLIC_API_BASE_URL=/api/v1`.
  TODO(AUTH-001): decide this together with the auth design — cookie sessions strongly favour
  same origin.

---

## Not decided yet

| Item | Owner |
|---|---|
| Hosting: VPS with Dokploy alongside the backend, or Vercel | Loopify + backend developer |
| Staging URL and seed data refresh | Backend developer |
| Error monitoring (Sentry / GlitchTip) | Loopify |
