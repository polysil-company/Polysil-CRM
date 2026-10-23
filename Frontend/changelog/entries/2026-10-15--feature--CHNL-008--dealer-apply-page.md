---
date: 2026-10-15
type: feature
title: "The dealer applicant's own page: verify, fill in, upload, submit"
dataIds:
  - CHNL-008
author: Nakul Srivastava
breaking: false
---

## Before

A dealer application's link (`apply_url`) points at `/dealer-apply/<token>` on this app. The backend serves the applicant through the `/public/dealer-apply/{token}` calls, and they need no account:

- the outline without a session;
- a WhatsApp code, which answers a two-hour session sent as `X-Apply-Session`;
- the fields, a GSTIN check, documents and submit.

The frontend had no such page, so the link the staff send (PR #145) opened nothing.

## Now

- **`/dealer-apply/<token>`**, public and phone first, in the same layout as the customer's quotation link. Open to visitors who aren't signed in, like `/q/`.
- **Verify your mobile:**
  - the firm and the masked mobile, then "Send the code on WhatsApp";
  - the 6-digit code, with "Send a new code";
  - a wrong code, or a code asked for within a minute, is said in words.
- **The form**, once verified:
  - the same fields as staff's Edit details (`DealerFieldsEditor`, shared), saved as the applicant goes;
  - **Check GSTIN** says whether it is valid, its PAN, and the GST record's name when there is one;
  - a returned application shows Polysil's remark.
- **Documents:**
  - upload the GST certificate, PAN card, cancelled cheque, shop photo, shop licence, or "Other" with a name (JPEG, PNG, WebP, HEIC or PDF, up to 10 MB);
  - the applicant's own uploads can be removed; staff uploads show without Remove.
- **Submit the application** once nothing is missing. Otherwise it says what's still needed, or "Save your changes first".
- **Other states:**
  - a submitted application: "Submitted, we will be in touch";
  - an expired, replaced or closed link: "This link doesn't work any more";
  - a session that ends (`403 no_session`): verify again, keeping what was saved.
- **The API client** takes `applicantSession`, sent as `X-Apply-Session`. It is a narrow option, not a general header.
- **The mock:**
  - the public calls, with the mock sign-in's code;
  - a code at most once a minute, and the session;
  - the outline and the full view;
  - field checks shared with staff, documents, and submit;
  - fixed links for the seeds (`apply-demo-1` to `-3`), so a demo survives a reload.
- Checked on a phone in light and dark mode: verify, the form with a GSTIN checked, a document uploaded, and a submitted one. axe found nothing after the empty states' headings were made level 2.

## Discussion

- **Stacked on #145** (dealer applications for staff), which is stacked on #132. Merge in that order and retarget each to `integration` first.
- **The session is kept in the page only, not in storage.** Reopening the link asks for a code again. What was saved stays on the backend.
- **The GSTIN check reads the GSTIN itself** until the backend has a GST data provider (GAP-292). The applicant types the firm's name.
- **Not yet checked on staging,** nor with a real WhatsApp code.

## Files changed

- `src/app/(public)/dealer-apply/[token]/page.tsx`: new route.
- `src/features/dealer-applications/api/dealer-apply.schemas.ts`, `dealer-apply.api.ts`: new; the applicant's calls.
- `src/features/dealer-applications/api/dealer-applications.queries.ts`: the applicant's view and GSTIN check.
- `src/features/dealer-applications/components/dealer-apply-page.tsx`, `dealer-apply-form.tsx`: new; verify, the form, documents and submit.
- `src/features/dealer-applications/lib/dealer-application-labels.ts`: the document labels.
- `src/lib/api/client.ts`: `applicantSession`.
- `src/lib/auth/redirects.ts`: `/dealer-apply/` is open.
- `src/mocks/handlers/dealer-applications.ts`, `src/mocks/data/dealer-applications.ts`: the public mock.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CHNL-008.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/public/dealer-apply-*`: records and screens.

## Tests

- `src/features/dealer-applications/components/dealer-apply.test.tsx`:
  - the outline until verified, a wrong code refused, then every field;
  - a write refused without a session; submit refused while something is missing, then accepted;
  - the page: a wrong code said in words, verify, save, upload;
  - a returned one's remark; a dead link; a submitted one.
- `src/lib/api/client.test.ts`: `X-Apply-Session` is sent only when given.
- `src/lib/auth/redirects.test.ts`: `/dealer-apply/` opens without a session.
- Walked through in the mock on a phone, light and dark.
