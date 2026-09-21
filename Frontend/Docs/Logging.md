# Logging

**Code:** [`src/lib/logger`](../src/lib/logger) · **Data ID:** OBS-001

Every action that can fail is logged in one format, controlled at runtime by a single environment
variable — `LOG_LEVEL` — with no rebuild.

---

## The format: File → Function → Request → Response

```
INFO [LEAD-001] features/leads/api/leads.api.ts → listLeads → ← GET /leads 200 · 132ms · req 3f2a9c1e-…
```

| Part | Meaning |
|---|---|
| `INFO` | Level |
| `[LEAD-001]` | Data ID — the functionality (see [Data-IDs.md](Data-IDs.md)) |
| `features/leads/api/leads.api.ts` | File, relative to `src/` (lint-checked, cannot drift) |
| `listLeads` | Function, hook or handler |
| `← GET /leads 200` | What happened |
| `132ms` · `req …` | Duration and request ID |

In the **browser** each line is a collapsible console group containing the request, response,
error and the full structured record. On the **server** it is one JSON object per line (readable
text in local development), ready for a log collector.

---

## Levels

| Level | Used for | Default in |
|---|---|---|
| `debug` | Request payloads, response bodies, action start | development, feature previews |
| `info` | Successful requests and actions (summary only) | staging |
| `warn` | 4xx responses, degraded behaviour (mocks unavailable) | production |
| `error` | 5xx, network failures, timeouts, contract violations, render crashes | — |
| `silent` | Nothing | — |

---

## How to log

You rarely call the logger yourself — the building blocks do it:

| You use | It logs automatically |
|---|---|
| `apiRequest()` | Request (debug), response (info), failure (warn/error), `CONTRACT_VIOLATION` (error) |
| `useAsyncAction()` | Action start, success with duration, failure |
| TanStack Query caches | Any failure that did not come through `apiRequest()` |
| `error.tsx` / `global-error.tsx` | Render crashes with the Next.js digest |

When you do log, create one logger per file and name the function:

```ts
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "features/leads/components/new-lead-dialog.tsx", dataId: "LEAD-002" });

log.info("handleImport", "imported leads", { context: { rows: 42 } });
await log.trace("handleExport", () => exportLeads(params)); // start, success or failure, duration
```

Rules:

- **Every feature logs through `createLogger`.** `console.*` fails lint everywhere except the console
  transport.
- **Log actions that change data or can fail.** Not hovers, not menu toggles.
- **Put data in fields, not in the message:** `{ request, response, error, context }`.
- **Never log secrets on purpose.** Redaction is a safety net, not a licence.

---

## Redaction — automatic

Before any record reaches a transport, `redact()`:

- removes values under keys such as `password`, `otp`, `pin`, `token`, `secret`, `authorization`,
  `cookie`, `apiKey`, `aadhaar`, `pan`, `accountNumber`, `ifsc`, `cvv`, `upi` (and anything ending in
  `token`, `secret`, `password`)
- masks phone numbers to the last 4 digits (`******5678`) and emails to `r***@example.com`
- truncates long strings, large arrays and deep objects, and survives circular references

New sensitive field in the API contract? Add it to `redact.ts` and its test.

---

## Changing the level at runtime

### For everyone — server and all browsers

1. Set `LOG_LEVEL=debug` on the host (Dokploy / Docker env, Vercel project settings).
2. Restart the app (Docker) or redeploy (Vercel binds env vars at deploy time).
3. The server logs at the new level immediately. `src/proxy.ts` copies the level into the
   `polysil-log-level` cookie on each page request, so **browsers follow on their next navigation**.

Remember to set it back — `debug` is verbose.

### For one browser — live debugging, any environment

Open the browser console:

```js
polysilLogger.setLevel("debug"); // this browser only
polysilLogger.getLevel();
polysilLogger.setLevel(null);    // back to the server-controlled level
```

Outside production the account menu also has **Console logs**.

---

## What is not solved yet

TODO(OBS-001): browser logs only exist in the user's own console. For production debugging of other
people's sessions, add a remote transport (`registerLogTransport`): Sentry (free tier) or self-hosted
GlitchTip for errors, and an OpenTelemetry collector for logs. Decide together with hosting.
