---
date: 2026-10-09
type: feature
title: Lead QR codes and the public enquiry page
dataIds:
  - LEAD-013
  - LEAD-014
author: Nakul Srivastava
breaking: false
---

## Before

A farmer could only become a lead through staff, who typed them in. Two pieces were missing from the web app, though the backend served both (handover `public-lead-capture-contract.md`, and since #66 a `PATCH` for codes):

- The QR codes the client wants on dealer counters, fair stalls and leaflets.
- The public form those codes open.

## Now

- **QR codes** (Sales → QR codes, for staff who can see leads).
  - Each code shows as a scannable QR, black on white in both themes. It also shows:
    - its name, whether it is on, and its six-character code;
    - how many leads it brought;
    - its campaign, dealer, area and age.
  - **New QR code** (`leads.create`): name, campaign, dealer and area.
  - **Download to print** saves a 1024-pixel PNG. **Copy link** copies its address.
  - **Edit** and **Switch off/on** (`leads.edit`). The code and its link never change, so printed copies keep working. A switched-off code's scans become plain website enquiries.
  - A dealer the backend refuses is named on its field.
  - States: skeleton, "No QR codes yet", and a phone in dark mode.
- **The enquiry page** (`/enquiry`, no sign-in, made for a phone).
  - "Enquiry through <dealer>" shows when a code opened it.
  - The farmer gives:
    - their name and mobile;
    - their area: state, then district, then an optional taluka. A code's area is used as it is, with "Choose another area";
    - their village, the system they want, how they'll buy, and a note.
  - **Send me a code on WhatsApp**, then the six digits:
    - the time left, and "Send a new code" after a minute;
    - "Change my details";
    - a wrong or expired code says so, and too many codes says to wait.
  - Then the inquiry number to keep. The same number comes back when the mobile already enquired today. The page says the WhatsApp copy can be held back, so this is where to read it.
  - A code no longer in use opens the plain form and says so.
  - Checked at 360 px, light and dark, with no sideways scroll.

## Discussion

**Decisions:**

- **`qrcode.react` 4.2.0 draws the codes.** It has no dependencies, is ISC-licensed, and supports React 19. It renders an SVG (and a hidden canvas for the download), so no HTML is injected. It was the smallest option that fits both uses.
- **A new token, `bg-scan-surface`.** It is white in both themes, because a camera can't read a QR on charcoal. It is explained in `Docs/Design-System.md`, and no interface colour changed.
- **`/enquiry` is an open path,** an exact match, beside the `/q/` customer link. Signed in or not, nobody is redirected.
- **The QR codes screen is under Sales.** The codes make leads, and whoever can see leads can see their codes.
- **The form needs a district, not a taluka.** The backend takes a district or a taluka, never a state.

**The mock:**

- The mock sends no WhatsApp: any six digits match except `000000`, which stands for a wrong code.
- After five codes to one number it answers `429`.
- A lead from a code is credited to the code's dealer, as the backend does.

## Files changed

- `src/features/lead-capture/`: new.
  - `api/`: schemas, API, queries, mutations, and `lead-capture.test.ts`.
  - `components/qr-codes.tsx`: the staff screen and its form.
  - `components/enquiry-form.tsx`: the public page.
  - `components/lead-capture-ui.test.tsx`: the UI tests.
- `src/app/(app)/qr-codes/`, `src/app/(public)/enquiry/`: the routes.
- `src/components/layout/navigation.ts`: QR codes under Sales.
- `src/lib/auth/redirects.ts` and its test: `/enquiry` opens without signing in.
- `src/styles/tokens.css`, `Docs/Design-System.md`: `scan-surface`.
- `src/mocks/`: `handlers/lead-capture.ts`, `data/lead-capture.ts`, the database, and `createLeadFrom` exported from the leads mock.
- `package.json`, `package-lock.json`: `qrcode.react` 4.2.0, pinned.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-013 and LEAD-014.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/lead-capture/`: the records.

## Tests

**`src/features/lead-capture/api/lead-capture.test.ts`:**

- `[LEAD-013]`: a code is made with an `/enquiry?qr=` link, then renamed and switched off with the same code; an unknown dealer is refused.
- `[LEAD-014]`:
  - a dealer's code names the dealer, and the lead is credited to it once the code matches;
  - the same mobile gets the same number;
  - a wrong code, and a code no longer in use, are refused.

**`src/features/lead-capture/components/lead-capture-ui.test.tsx`:**

- the list with counts and states; making a code, then a mistake; switching a code off;
- the whole enquiry through a dealer's code;
- the district is asked for;
- a wrong code;
- a code no longer in use.

**`src/lib/auth/redirects.test.ts`:** `/enquiry` opens signed in or out.

**By hand, in Chromium on the mock backend:**

1. QR codes as a State Manager: list, new code, download.
2. The list on a phone in dark mode.
3. The enquiry at 360 px in light (through to the number) and dark.
4. The empty form's mistakes on a desktop.

axe found nothing on any of these.
