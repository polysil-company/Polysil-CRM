# Pending features: plans for what comes next

Four things not built yet, each planned enough to start:

1. **The web app's backlog** (§1): what the backend already serves and the CRM has no screen for.
2. **The field mobile app** (§2), with location tracking.
3. **The Polysil website** (§3): a landing page, WhatsApp-verified access to the product range, and a request form.
4. **An in-app help assistant** (§4) that answers "where is…?" and "how do I…?" questions about the CRM.

Each section lists what it needs from the backend. Those are **proposals**: when a piece starts, file them in [`Backend-Tasks.md`](Backend-Tasks.md) as `BE-NNN` tasks, and register Data IDs in `Frontend/src/lib/data-ids/registry.ts` before writing code (`Frontend/AGENTS.md` §6).

_Last updated: 3 October 2026, against `integration` at `208eae9` (backend #50)._

---

## 1. Web app backlog: the backend is ready, the screens aren't

The backend ships 21 modules and 188 endpoints (`backend/docs/api/README.md`). The CRM covers Approvals, Auth, Dashboard, Messages, Notifications and Quotations, most of Leads and Orders, and the lookups its forms need. This is what's left, in a suggested order.

| # | Feature | Who uses it | Backend | Size |
| --- | --- | --- | --- | --- |
| 1 | **Pick-ups from backend #49 and #50:** an **Area** filter on the leads list (state → district → taluka, with counts, several at once; `GET /leads/areas`, `territory_id` as a list), the asker's reason in the Approvals inbox (`request_remark`), and dealer search by contact person | Managers | done | S–M |
| 2 | **Tasks, planner and meeting minutes:** today's follow-ups, a calendar, the team planner for managers, minutes of a meeting on a lead. The dashboard's follow-ups and the lead list's empty Follow-up column wait on this. | Field officers, managers | `tasks.md` (13 endpoints), `tasks-and-planner-contract.md` | L |
| 3 | **Complaints:** register a complaint against an order, check it, quality check (QC), the remedy (a refund through approval, a replacement order, or none), SLA policies, attachments, stats. Refund steps then join the Approvals inbox. | Field officers, QA, Accounts | `complaints.md` (20 endpoints), `complaints-contract.md`, `complaint-remedies-contract.md` | L |
| 4 | **Leads, the rest:** edit and delete a lead; the duplicates queue (dismiss or merge); QR codes for printed material, and the public enquiry page `/enquiry` (see §3, which reuses it) | Field officers, managers | `leads.md`, `public.md`, `public-lead-capture-contract.md` | M |
| 5 | **Direct orders (SO-005):** an order typed item by item, not from a quotation; one combined order for a dealer; the orders' stats | Field officers, dealers | `orders.md` (`lines`, `PUT /orders/{id}/lines`, `/orders/stats`) | M |
| 6 | **Operations queues:** a **Dispatch queue** (every order waiting to ship, `GET /dispatches`) and an **Accounts queue** (orders waiting on the payment check) | Dispatch, Accounts | `dispatch.md`, `orders.md` | S–M |
| 7 | **Subsidy:** the subsidy calculator, then applications through their stages, with documents and the PIMS Excel export | Field officers, subsidy desk | `subsidy.md` (4), `subsidy-applications.md` (13), handovers | L |
| 8 | **Administration (masters):** users (create, roles, unlock, reset password, sign out everywhere, hand over leads when someone leaves); offices; territories; channel partners; products, HSN and tax rates; price lists (draft, items, publish); the admin lists (lead sources, crops, lost reasons, meeting and complaint types, lead scoring) | Admin | `users.md`, `org-units.md`, `territories.md`, `partners.md`, `products.md`, `pricing.md`, `lookups.md` | L |
| 9 | **Dealer portal screens:** what a dealer, distributor or sub-dealer sees after signing in with their mobile code: their leads, quotations, orders and dispatch status | Channel partners | mostly the same endpoints, scoped by the backend | M |

Not on the backend yet, so not in this list: reports and exports, schemes and promotions, marketing campaigns, the location features of §2, the website catalogue of §3.

**Suggested next three:**

- **Item 1:** small, and the managers asked for the area filter in the demo.
- **Item 2:** tasks unlock the follow-up figures already on the dashboard and the lead list.
- **Item 6:** small, and gives Accounts and Dispatch their own working screens.

---

## 2. The field mobile app

### What it is for

Field officers and their managers spend the day travelling. The app has to:

- work on a phone with a weak connection;
- record visits with proof (GPS and a photo);
- track the route between punch-in and punch-out.

The web app stays for desk work. Background location can't be done from a web page: browsers stop location updates when the screen locks or the user switches apps, and service workers have no location access. That is why this is a native app.

### Decisions already taken (`Frontend/Docs/Plan.md`)

- **One app** for executives and managers. The manager screens are role-based and lazy-loaded (ADR-017).
- **Built with Expo (React Native) and TypeScript.** It shares the `/api/v1` contract with the web.
- **Android first.** Shared with staff directly as a signed APK or through managed Google Play, which avoids the Play Store's slow background-location review (R2, ISS-011). iOS later.

### Scope

| Phase | Delivers | Plan ref |
| --- | --- | --- |
| **M0 · Foundation** | Expo project with Expo Router, TypeScript strict, Zod. The web's API contracts move into a shared package so both apps validate the same shapes. Sign-in (email and password; OTP), with tokens in `expo-secure-store`. App shell with role-based tabs. A real-device build through EAS, and the internal distribution pipeline proven end to end. Crash reporting. | W3 mobile |
| **M1 · Leads in the field** | Today's list; the lead list and page; **capture a lead offline**, with the GPS of where it was captured; notes; stage changes. An **outbox**: actions are stored on the phone and sent when there's signal. Every POST already takes an `Idempotency-Key`, so a retry never duplicates. | W4 mobile |
| **M2 · Day plan** | Tasks and the planner (§1 item 2's API), visit logging, minutes of a meeting. | W4 mobile |
| **M3 · Attendance and visits** | **Punch in and out** with GPS and a selfie. **Check in and out of a visit** at the farmer's place, with GPS and a photo. Distance from the lead's location is shown, and flagged if too far. (REQ-701) | W4 mobile |
| **M4 · Route tracking** | Between punch-in and punch-out only: background location through `expo-location` and `expo-task-manager`, with an Android **foreground service** and its visible notification ("Polysil is tracking your route"). Points are buffered on the phone and uploaded in batches. The backend works out the distance, skipping inaccurate points and impossible jumps. The route for the day, and km travelled. (REQ-702) | W4 mobile |
| **M5 · Manager** | A team map (last known positions during working hours), each person's route and visits, visit compliance, and push notifications for approvals and assignments. (REQ-703) | W5 mobile |
| **M6 · Pilot and hardening** | 5–10 officers for a week on real phones. Battery, data and accuracy measured; fixes; then roll-out. | W6 |

### What the backend needs to add

The backend has **none** of these yet. These are proposed asks.

- **Attendance:** `POST /attendance/punch-in`, `POST /attendance/punch-out` (time, GPS, accuracy, selfie), and a daily list for managers.
- **Location ingest:** `POST /locations/batch`, taking up to a few hundred points (time, lat, lng, accuracy, speed, battery), idempotent per batch.
- **Route summary:** `GET /attendance/{day}/route` with the cleaned polyline and **distance in km**, computed on the server. Snapping to roads is optional, through OSRM self-hosted or Google Roads.
- **Visits:** check-in and check-out on a lead, with GPS and a photo, through a file upload endpoint and its storage.
- **Team map:** `GET /team/locations`, the last known point per person in the manager's scope, during working hours only.
- **Push:** register the device's push token, and send notifications through Expo push or FCM.
- **Privacy:** location stored only between punch-in and punch-out; a retention period (e.g. 90 days); who may see whose route, by role scope.

### Risks and how we handle them

| Risk | Handling |
| --- | --- |
| Phone makers (Xiaomi, Oppo, Vivo, Realme) kill background apps to save battery | An onboarding screen walks the user through "no battery restrictions" for their phone model. The app shows a "tracking paused" warning; the backend flags gaps in a route. |
| Google Play's background-location review | Internal distribution, as planned (R2). |
| GPS accuracy and battery drain | Adaptive intervals: often while moving, rarely while still. Drop points with accuracy worse than about 50 m. Measure it in the M6 pilot. |
| Privacy and consent (India's DPDP Act 2023) | Explicit consent at first launch; tracking only while punched in; a visible notification; a written retention policy agreed with the client. |
| Offline conflicts | The outbox with idempotency keys; the server wins, and a refused action is shown to the user with the reason. |

### Questions for the client

1. **Is the km travelled used for travel allowance?** If so, should it be cross-checked against odometer photos at punch-in and punch-out?
2. **Selfie at punch-in:** yes or no?
3. **Phones:** company-issued or personal? (This decides how strict the battery and permission setup can be.)
4. **iOS:** needed in year one?
5. **Working hours,** and whether tracking may run outside them.

---

## 3. The Polysil website: landing page, catalogue and requests

### What it is for

A public website for Polysil. It explains who they are and what they make. A visitor (a farmer, dealer or contractor) **verifies their mobile number through WhatsApp**, then sees the full range of materials and products, picks what they're interested in, and **sends a request**. The request arrives in the CRM as a lead, so the right officer follows it up.

### The flow

1. **Landing page.** About Polysil, the main product families (drip, sprinklers, pipes, fittings, automation), why drip irrigation, government subsidy in brief, dealers and service, contact. One clear call to action: **"See our full range and get a quote."**
2. **Mobile number:** the visitor enters it and a 6-digit code arrives on WhatsApp.
3. **Code:** the visitor types it in. The number is now verified for this visit (e.g. 24 hours on this device).
4. **The catalogue:** families → products, each with photos, sizes and specifications, and brochures as PDFs. Prices only if the client wants them shown (an open question).
5. **The request:** the visitor ticks products (with rough quantities), adds name, place (district → taluka), land, crops and a note, and presses **Send request**.
6. **Thank you:** the inquiry number, "keep it", and a WhatsApp copy. In the CRM it is a lead from source **website**, with the products listed, owned by the officer for that area.

### What already exists

The backend shipped the public enquiry flow (`backend/docs/handover/public-lead-capture-contract.md`):

- `GET /public/lead-form`, the form's choices;
- `GET /public/territories`, the place pickers;
- `POST /public/leads/verify`, which sends the WhatsApp code (limited in rate);
- `POST /public/leads`, which checks the code and creates the lead.

QR codes for printed material are included too. **Steps 1–2 and 5–6 can start now.**

### What the backend needs to add

- **A verified visitor session.** Today the code is consumed in the same call that creates the lead, which suits a one-shot enquiry. To browse a catalogue after verifying, the backend needs `POST /public/session/verify`, returning a short-lived visitor token (24 hours, tied to the mobile number) that the catalogue and request calls accept.
- **A public catalogue:** `GET /public/catalogue`, with families, products, images, specifications and brochure links, readable only with a visitor token. Maybe prices, depending on the client's answer. It needs image and brochure storage, and admin screens to manage the content (§1 item 8 covers products already).
- **A request with products:** `POST /public/leads` takes a list of products and quantities, shown on the lead.
- **Website content:** either the text and images live in the website's code (simplest; changed through a pull request), or the backend serves a small content API so the client can edit it. Start in code.

### How we'd build it

- **Same Next.js codebase, as its own route group** (`(site)`), in line with ADR-001. The public quotation page `/q/{token}` already lives this way. The landing and catalogue pages are **statically generated** for speed and search ranking, with the site's own domain (e.g. `polysil.in`) pointed at them.
- **Built for Indian mobile networks:** mobile first, light pages, compressed images (Next.js Image with AVIF/WebP), no heavy animation libraries on the landing. Lighthouse budget: 90+ on a mid-range Android over 4G.
- **SEO:** metadata, Open Graph images, a sitemap, structured data for the organisation and products, and Google Business links.
- **Languages:** English first. **Gujarati and Hindi are an open question** that changes the plan: farmers read Gujarati far more than English. If yes, set up translation (`next-intl`) from day one.
- **Analytics:** page views and the funnel (landing → verify → catalogue → request) with Vercel Analytics or a free, privacy-friendly alternative.
- **Abuse:** the backend already limits codes per number and address; add a honeypot field. Each WhatsApp message costs money, so watch the count.

### Phases

| Phase | Delivers |
| --- | --- |
| **W1 · Landing and enquiry** | The landing page, and the WhatsApp-verified enquiry on today's API. A lead arrives in the CRM. The QR code screens for staff ship with it. |
| **W2 · Catalogue** | After the backend's session and catalogue: verify, browse, request with products. |
| **W3 · Polish** | SEO, analytics, performance budget, translations if chosen, a content review with the client. |

### Questions for the client

1. **Content:** text, product photos, brochures and the logo. Who provides them, and by when?
2. **Prices on the website:** none, list prices (MRP), or "on request"?
3. **Languages:** English only, or Gujarati and Hindi as well?
4. **Domain:** which one, and who controls its DNS?
5. **Who may verify:** farmers only, or dealers and contractors too, with a different journey?

---

## 4. In-app help assistant (chatbot)

### What it is for

A small chat panel inside the CRM for questions about **using the app**. It does not touch business data. For example:

- "Where are my leads?" → "Sales → Leads." [Open Leads]
- "How do I ask for a discount approval?" → the steps, with a link to the quotation page.
- "What does Dormant mean?" → the stage explanation.
- "Why can't I see Approvals?" → it depends on the role.

It answers from the app's structure (the menu, the pages, each role's permissions) and from the written flows. It never reads leads, quotations or orders, so it can't leak data or make up figures.

### Where its knowledge comes from

Everything comes from files we already keep, regenerated whenever they change:

- **The menu and pages:** `Frontend/src/components/layout/navigation.ts`, filtered to the **signed-in user's permissions**, so it never points someone to a page they can't open.
- **The flows:** `Frontend/Docs/Demo-Guide.md` (the click-by-click flows) and `Frontend/Docs/Tested-Features.md` (what each feature does).
- **The stage meanings and labels:** `lead-labels.ts`, the same text the app shows.

This is small enough (a few thousand words) to send with every question, so there is no search index to run. That keeps it simple, cheap and easy to check.

### How it works

1. A **"Help" button** in the top bar opens a side panel. The page the user is on is sent with the question, so the assistant can answer in context.
2. The question goes to **our own server route**, a Next.js route handler that holds the AI key. That route:
   - checks the user is signed in;
   - builds the knowledge for their role;
   - calls the model, which streams the answer back.
3. **Answers can include page buttons,** but only from the real list of routes. A link the model invents is dropped.
4. **Questions about data** ("how many leads do I have?") get a pointer to the page that shows it, not a number.
5. **Limits:** per-user rate limiting; questions logged without personal data, as in `Frontend/Docs/Logging.md`; a "Was this helpful?" thumbs up or down.

### Model and provider

Behind one small interface, so it can be swapped:

- **Google Gemini:** the team's usual choice, with a free tier.
- **Anthropic Claude:** for example Haiku 4.5, fast and inexpensive for short answers.

Pick after a short trial on the question set below.

### Quality checks

A test set of 40–60 real questions, each with the expected page or steps, runs before every release. It includes trick questions: about data, about pages the role can't see, and off-topic ones. Show it to a few users and add their real questions to the set.

### Phases

| Phase | Delivers |
| --- | --- |
| **A1** | The knowledge builder (the menu, filtered by role, plus the guides), the server route, and the panel with streaming and page buttons |
| **A2** | The question set and the release check, rate limits, feedback |
| **A3** | Context: "what can I do on this page?" from the current route; Gujarati and Hindi if the website goes that way |

### Questions for the team

1. **Provider:** Gemini or Claude, after the trial.
2. **Who can use it:** everyone, or staff only (not partners) at first.
