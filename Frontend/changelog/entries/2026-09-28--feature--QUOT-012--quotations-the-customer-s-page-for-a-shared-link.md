---
date: 2026-09-28
type: feature
title: "Quotations: the customer's page for a shared link"
dataIds:
  - QUOT-012
author: Nakul Srivastava
breaking: false
---

## Before

A sent quotation carries a customer link, `/q/{token}`, which the WhatsApp message also carries, but the app had no page there: a customer who tapped it was sent to sign in.

## Now

**The customer's page (QUOT-012)** — `/q/{token}` opens without signing in, for anyone, signed in or not. It is built for a phone, in one narrow column:

- **Quotation** and its number (with the version once there is more than one), **From** the seller and their GSTIN.
- **Total, including GST**, large; the number of items, the date sent and **Valid until**.
- **View quotation** opens the PDF in a new tab. Until the PDF is ready: "Preparing the PDF…", and the page checks again every few seconds.
- An expired quotation says so ("Prices may have changed; ask for a new one"), and a replaced one says a newer version was sent. Both still open.
- A link that doesn't match a quotation: "This link doesn't open a quotation", with what to do.

Nothing personal is on the page — no name, mobile, address or items — as the backend's contract requires: a forwarded link shows a number and a total.

## Discussion

- **The PDF opens only from the button, never on load.** Messengers fetch a link to draw its preview the moment it is sent; the backend records a view when the PDF is opened, so a page that fetched it would count every preview as the customer. The button is a real link, so it works however the phone opens it.
- **No sign-in, and no redirect:** `/q/…` is an open path in the sign-in routing (`isOpenPath`), for signed-out and signed-in visitors alike. The page calls only the backend's `/public` endpoint, without a token.
- **The token stays on the page:** the layout sets `referrer: no-referrer`, so the link's secret is not passed on when the PDF opens on another host.
- **The mock** serves the page for every sent quotation, and its share links now point at the app's own origin, so **Copy** on a quotation gives a link that opens here. Opening the PDF records the view (the first moves a sent quotation to Viewed). The browser opens that link in a new tab, which the mock cannot answer (it has no PDFs), as with **Open PDF** — `TODO(QUOT-012)`.
- **Backend:** BE-015 (`PUBLIC_WEB_URL`) decides where the real links point; until it is set, links from the dev API open localhost.
- **Next:** the approvals inbox's quotation rows, with APPR-001.

## Files changed

- `src/app/(public)/layout.tsx`, `src/app/(public)/q/[token]/page.tsx` — new: the route group for signed-out pages and the customer's page
- `src/features/quotations/components/shared-quotation.tsx` — new: `SharedQuotation` and its skeleton
- `src/features/quotations/api/quotations.schemas.ts`, `quotations.api.ts`, `quotations.queries.ts` — the public quotation contract, `getPublicQuotation` (no token), and its query, re-reading while the PDF renders
- `src/lib/auth/redirects.ts` — `/q/…` is an open path
- `src/lib/api/url.ts` — `asApiPath`, for a path an API response hands back
- `src/mocks/handlers/quotations.ts` — `GET /public/q/{token}` and `GET /public/q/{token}/pdf`; `src/mocks/data/quotations.ts` — share links on the app's origin
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — QUOT-012
- `Docs/Plan.md` — §9: the public page connected
- `e2e/smoke.spec.ts` — the link opens signed out, with no accessibility violations

## Tests

- `src/features/quotations/components/shared-quotation.test.tsx` — `[QUOT-012]` read without an `Authorization` header and with nothing personal; an unknown link is 404; the number, total and a new-tab link to the PDF; "Preparing the PDF…" with no link; expired and replaced, still opening; an unknown link explained
- `src/lib/auth/redirects.test.ts` — `[AUTH-006]` a quotation link opens signed in or out; `/quotations` still needs a session
- `e2e/smoke.spec.ts` — `[QUOT-012]` opens signed out on desktop and phone, the link opens a new tab, `no-referrer`, and axe finds no violations
- By hand (`npm run dev`): sign out, open `/q/mock-3`, then `/q/anything`; signed in, copy a quotation's customer link and open it. At 360px and on a wide screen, in light and dark.
