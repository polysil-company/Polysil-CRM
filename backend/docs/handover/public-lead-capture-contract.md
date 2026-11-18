# Public Lead Capture Contract - the enquiry page and QR codes

> **Status: shipped.** The generated reference is `backend/docs/api/public.md` (the four public endpoints) and `backend/docs/api/leads.md` (`/lead-qr-codes`). This page is the context around them.

## What to build

1. **A public enquiry page at `/enquiry`** on the web app. No sign-in. Mobile-first.
2. **The same page with `?qr=CODE`**, which a printed QR code opens. It shows "Enquiry through <label>" at the top.
3. **A QR codes screen for staff:** a list with lead counts, a "New code" form, and printing (draw the QR image from `url`).

## The enquiry page, step by step

| Step | Call | Notes |
|---|---|---|
| 1. Load | `GET /public/lead-form?qr=CODE` (qr optional) | returns `qr` (label, campaign, a territory to preselect), `states`, `mis_systems`, `inquiry_types`. `404` means the QR code is not in use: show the plain form |
| 2. Pickers | `GET /public/territories?parent_id=<state>` then `?parent_id=<district>` | districts, then talukas. The lead needs a **district or taluka**, never a state |
| 3. Mobile | `POST /public/leads/verify {mobile}` | always `202` with `expires_in` (600) and `resend_after` (60). Offer "send again" after `resend_after`. `429 rate_limited`: too many codes for this number or address, ask them to wait |
| 4. Code and details | `POST /public/leads {mobile, code, farmer_name, territory_id, village, mis_system, inquiry_type, note, qr}` | `201 {inquiry_no, created: true}`. `200 {inquiry_no, created: false}`: this mobile already enquired today, or it is a retry; show the number either way. `422 invalid_code`: wrong, expired or used up, offer a new code. `422` with `fields.territory_id`: choose a district or taluka |
| 5. Thank you | none | show the inquiry number and "keep it". Say the WhatsApp message is a copy: it can be held back if the farmer was already messaged today, so the page is where they read the number |

Send the `qr` value from the page URL on step 4. The mobile can be typed any Indian way (`9876543210`, `+91 98765 43210`).

## QR codes (staff)

| Call | Notes |
|---|---|
| `POST /api/v1/lead-qr-codes {label, campaign?, partner_id?, territory_id?}` | needs `leads.create`; `Idempotency-Key` required. Returns `code` (6 characters) and `url` (`<web app>/enquiry?qr=<code>`). Draw the QR from `url`. `422` with `fields.partner_id: not found` when the dealer is closed or outside your area: offer only dealers from `GET /partners` |
| `GET /api/v1/lead-qr-codes` | the codes in your scope, newest first, each with `lead_count` |

A code with a `partner_id` credits its leads to that dealer. A code with a `territory_id` preselects it in the picker. If the dealer is later closed, the printed code still captures leads, as plain website leads.

## In the lead list

Public leads have `source` `website` or `qr_code`; filter with `GET /leads?source=website`. They are owned by the officer covering the territory, or unassigned (`owner=none`) when nobody covers it. The creator shows as "Website and QR".

## Not yet

- Editing or deactivating a QR code (a `PATCH` follows).
- WhatsApp messages as a lead source (waits on the 11za webhook settings).
