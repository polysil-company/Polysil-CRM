---
date: 2026-09-15
type: feature
title: Sign-in for staff and channel partners, sessions that stay signed in, and permission-based navigation
dataIds:
  - AUTH-001
  - AUTH-002
  - AUTH-003
  - AUTH-004
  - AUTH-005
  - AUTH-006
  - OBS-002
  - APP-001
  - APP-002
  - DS-001
author: Nakul Srivastava
breaking: true
---

## Before

Anyone could open every page: there was no sign-in, and "Sign out" in the account menu was disabled. The signed-in user came from a placeholder `GET /me` shape invented by the frontend, and a hard-coded role → permission matrix decided the navigation. The API client sent no credentials, and its default base URL pointed at a separate origin (`http://localhost:4000`), which could never carry the backend's refresh cookie.

## Now

**Signing in** — `/sign-in`, with a choice that lives in the URL (`?method=staff`):

- **Channel partners (AUTH-001)** enter their mobile number, typed any common way (`98765 43210`, `+91…`, `0…`). The next step never claims a code was sent — only that one is on its way if the number is registered, as the backend requires. The code field accepts typing, pasting (`482 913`) and the phone's SMS autofill, and signs in as soon as the sixth digit arrives. A countdown shows when the code expires and when a new one can be requested; an expired code disables the field. A wrong code clears the field, keeps focus and explains what to do. "Change number" returns with the number kept.
- **Staff (AUTH-003)** use their work email and password, with a show-password toggle and a Caps Lock warning. A rejected password clears only the password and focuses it. A locked account (5 failures in 15 minutes) says so. Unexpected failures show a copyable reference.
- Every button shows progress, success or failure and cannot double-submit. Validation errors from the backend (422) land on the field.
- Wide screens add a teal brand panel with slowly dripping irrigation lines; phones get the form alone. Both themes, 360px upwards, reduced motion respected (no drops drawn).

**Staying signed in (AUTH-004)** — the access token is held in memory only; the backend's httpOnly cookie renews it. The token is refreshed a minute before it expires, when the tab becomes visible and when the connection returns. A request that still meets an expired token refreshes and retries once, and simultaneous requests share one refresh. A reload restores the session with a short "Opening your workspace" screen. If the backend cannot be reached, an error with a retry appears instead of a false sign-out.

**Leaving (AUTH-005, AUTH-006)** — "Sign out" in the account menu works. Signing out, or a session the backend ends, clears all cached data and opens sign-in — in every open tab. After an expiry the visitor returns to the page they were on; after a deliberate sign-out they see "You've signed out". Visiting any page without a session goes straight to sign-in and back afterwards; the return path can never point to another site.

**Who sees what (AUTH-002)** — the account menu, sidebar, command menu, sales tabs and "New lead" follow the `permissions` list from `GET /auth/me` instead of a role matrix. The account menu reads "District Manager · Vadodara District" or "Dealer · Shah Agro Traders".

**Mock backend** — all six `/auth` endpoints, built from the backend's contract: demo password `polysil-demo`, demo code `123456`, lockout, code attempts, refresh rotation, and a permission matrix per role that follows the client's visibility rules. The role switcher and slow scenario still work; auth ignores the error scenario so nobody gets locked out.

**Fixed while previewing (APP-002, APP-001)** — opening the theme menu or the account menu crashed the page ("MenuGroupContext is missing"): each menu's section heading sat outside the group it names. Both headings now sit inside their group, which also names the group for screen readers. The theme script in the page head no longer triggers React's "script tag while rendering" warning when the layout re-renders in the browser. Both menus also nudged sideways just after opening: they open on mouse-down, while the button's press animation has shrunk it, and followed the button as it grew back. A button no longer shrinks while its own popup is open, so menus, popovers and selects stay put.

## Discussion

- **Contract source:** `backend/docs/api/auth.md` and `backend/api/schemas/auth.py` on `backend-foundation`. Nothing was invented beyond what they state; unknowns are marked `TODO(AUTH-002)`.
- **Same origin (breaking):** the browser now calls `/api/v1`, and `next.config.ts` rewrites it to `API_PROXY_TARGET` (default `http://127.0.0.1:8000`). The backend has no CORS and scopes its refresh cookie to `/api/v1/auth`, so a separate origin would lose every session. `NEXT_PUBLIC_API_BASE_URL` defaults to `/api/v1`; staging and production builds must set `API_PROXY_TARGET`.
- **Token in memory, not localStorage:** an injected script could read storage and keep the token. The cost is one refresh call per page load, which the gate covers with a brief loading screen.
- **Session marker cookie:** `proxy.ts` cannot see the refresh cookie (wrong path), so the frontend sets a secret-free `polysil_session=1` purely to redirect before a protected page renders. The Next.js authentication guide recommends exactly this split: an optimistic check in proxy, real checks next to the data.
- **Rejected:** a Next.js route handler that holds tokens server-side (a second session system to secure and keep in sync with the backend's); server-side prefetch (impossible while the token lives in the browser — tracked as `TODO(AUTH-006)`).
- **Permissions (breaking):** `can(role, "leads:create")` became `can(permissions, "leads", "create")`, and `useCan` changed the same way. Role codes now match the backend (`distributor`, `dealer`, `sub_dealer` instead of `channel_partner`). Module codes for unbuilt modules (`quotations`, `approvals`, `marketing`, …) are assumptions to confirm against the backend's RBAC matrix — `TODO(AUTH-002)`.
- **API client:** every mutation outside `/auth` now sends an `Idempotency-Key`, which the backend requires. `sensitive: true` keeps passwords, codes and tokens out of the logs.
- **Not done:** route-level guards for pages a user cannot view (AUTH-002); a password reset flow (the backend has no endpoint yet — the form says to ask an administrator); integration on staging.

## Files changed

- `next.config.ts` — `/api/v1` rewrite to `API_PROXY_TARGET`, validated
- `.env.example` — same-origin API base URL, new `API_PROXY_TARGET`
- `src/proxy.ts` — sign-in redirects before pages render, alongside the log-level cookie
- `src/lib/api/client.ts` — `auth` option, token provider, refresh-and-retry after 401, `Idempotency-Key`, `sensitive` logging, same-origin credentials
- `src/lib/api/url.ts`, `src/lib/api/errors.ts` — same-origin URLs in the browser; the backend's 422 `fields`
- `src/lib/env/client.ts` — default API base URL `/api/v1`
- `src/lib/auth/session-store.ts`, `tokens.ts`, `session-hint.ts`, `redirects.ts` — the session, token contract, marker cookie and safe redirects
- `src/lib/auth/permissions.ts`, `roles.ts` — module permissions from `GET /auth/me`; backend role codes
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — AUTH-001 and AUTH-002 updated; AUTH-003 to AUTH-006 registered
- `src/lib/format/duration.ts`, `src/hooks/use-seconds-until.ts` — countdowns on one shared timer
- `src/lib/dev/mock-settings.ts` — demo credentials, default partner role
- `src/components/ui/otp-input.tsx`, `password-input.tsx` — new primitives, with stories
- `src/styles/tokens.css` — `animate-caret-blink`
- `src/features/auth/` — sign-in screen, mobile and staff forms, error copy, session gate, sign-out hook, brand-panel drip lines, API calls and schemas
- `src/features/session/` — `GET /auth/me` contract and `useCan(module, action)`
- `src/app/(auth)/layout.tsx`, `src/app/(auth)/sign-in/page.tsx`, `src/app/(app)/layout.tsx` — sign-in route; signed-in pages behind the gate
- `src/components/layout/navigation.ts`, `app-sidebar.tsx`, `command-menu.tsx`, `user-menu.tsx` — permission-based navigation; working sign-out
- `src/features/leads/components/leads-toolbar.tsx`, `sales-tabs.tsx` — permission checks
- `src/mocks/handlers/auth.ts` (replaces `session.ts`), `src/mocks/data/sessions.ts`, `permissions.ts` — mock `/auth` backend
- `e2e/smoke.spec.ts` — signs in before each journey; sign-in, reload, sign-out and OTP journeys
- `Docs/Frontend-Architecture.md`, `Environments.md`, `Frontend-Scope.md`, `Design-System.md`, `Logging.md`, `AGENTS.md`, `README.md` — how auth works and how to use it

## Tests

- `src/lib/api/client.test.ts` — `[AUTH-004] apiRequest authentication`: token sent, refresh-and-retry, rejected session, no request without a session, pre-auth and optional auth, `Idempotency-Key`, sensitive logs
- `src/lib/auth/session-store.test.ts` — `[AUTH-004] session store`: never signed in, sign-in, retry after 401, revoked session, shared refresh, restore after reload, unreachable backend and retry, sign-out
- `src/lib/auth/redirects.test.ts` — `[AUTH-006]`: open-redirect refusals, sign-in links, proxy decisions
- `src/features/auth/components/auth-gate.test.tsx` — `[AUTH-006] AuthGate`: redirect with return path, page shown when signed in, cache cleared on session end, no return after sign-out
- `src/features/auth/components/staff-sign-in-form.test.tsx`, `mobile-sign-in.test.tsx` — `[AUTH-003]` and `[AUTH-001]`: validation, success, wrong password or code, lockout, unexpected failure, resend, expiry, change number
- `src/components/ui/otp-input.test.tsx`, `password-input.test.tsx` — paste, length, autofill attributes, toggle, Caps Lock
- `src/features/session/api/session.schemas.test.ts`, `src/lib/auth/permissions.test.ts`, `src/mocks/data/permissions.test.ts`, `src/components/layout/navigation.test.ts` — the `/auth/me` contract, `can`, the client's visibility rules, navigation
- `src/lib/format/duration.test.ts`, `src/lib/env/client.test.ts`, `src/lib/api/url-and-errors.test.ts` — countdown text, new defaults, same-origin URLs and 422 fields
- By hand: `npm run dev` → you land on sign-in. Try both methods (demo credentials above), a wrong password five times, reload a signed-in page, sign out, and sign out in one tab while another is open. Check at 360px and on a wide screen, in light and dark.
