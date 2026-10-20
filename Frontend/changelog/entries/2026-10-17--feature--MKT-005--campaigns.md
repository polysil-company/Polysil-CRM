---
date: 2026-10-17
type: feature
title: "Campaigns: the list and a campaign's summary for Marketing, and a
  campaign on leads and QR codes"
dataIds:
  - MKT-005
  - MKT-006
author: Nakul Srivastava
breaking: false
---

## Before

The backend tracks campaigns (FS-040; handover `campaigns.md`): the fairs, farmer meetings and drives that bring leads in, with their cost.

- Leads and QR codes can name one.
- The campaign performance report counts their leads and sales; that report was already on screen.

Nothing else had a screen. A QR code carried only a free-text "Campaign".

## Now

- **Channel → Campaigns** (`/campaigns`, MKT-005), for staff holding `campaigns`:
  - each campaign shows its kind, place, dates, how many leads it brought, and its planned or actual cost;
  - newest start first; search, the kind, and **Showing** (running, switched off, all) live in the URL.
- **A campaign** opens in a dialog:
  - leads, won, lost and open, sales on its leads, and cost per lead and per win;
  - the planned and actual cost, and **See its leads**, which opens the lead list filtered to it;
  - **Change**; **Switch off** or **Switch on**; **Delete**;
  - a campaign that leads or QR codes name can't be deleted (`campaign_in_use`). The dialog says so and offers **Switch off instead**.
- **New campaign** and **Change** take a name, kind, place, start and end dates, planned and actual cost, and a description.
  - A taken name (case ignored) and an end before the start are refused on their fields.
  - Someone who can't see cost doesn't see or send the cost fields.
- **A campaign on a lead (MKT-006):**
  - New lead and Edit lead have a **Campaign** picker of the running campaigns. Staff only: a dealer's leads carry none.
  - A campaign switched off since stays named on the lead, and stays on the picker while it is the lead's value.
  - The lead shows "Campaign: …" beside its source.
  - The lead list has a **Campaign** filter: any campaign, or **No campaign**.
- **A campaign on a QR code (MKT-006):**
  - The QR code form links a running campaign. Leads from the code get it.
  - The old free text stays as **Campaign note**.
  - The code's card names the linked campaign first.
- Every list and dialog has its loading skeleton, empty state, and error with retry.
- Walked through in the mock, with axe finding nothing:
  - Admin on a desktop in light mode: the list, a summary, a new campaign's checks, the filtered lead list, a QR code's campaign;
  - a lead and its Edit on a phone in dark mode.

## Discussion

- **A new permission module, `campaigns`.**
  - Any staff user lists campaigns for the pickers.
  - Cost shows only with `campaigns.view`.
  - Writes need `campaigns` create, edit or delete.
  - The backend seeds view for Admin Sales and the MD, and Marketing's full access through its permission table. The mock gives Admin everything.
- **Data IDs in the MKT domain** (MKT-005, MKT-006), next to marketing material.
- **The report already existed:** Campaign performance (RPT) was built earlier, so this PR doesn't touch it.
- Built to the backend's contract and checked against the mock only; not yet checked on staging.

## Files changed

- `src/features/campaigns/` — the contract, API, queries, mutations, labels, the page, the summary dialog, the form, the picker, and tests.
- `src/app/(app)/campaigns/page.tsx` — the route.
- `src/components/layout/navigation.ts` — Campaigns in Channel.
- `src/lib/auth/permissions.ts` — the `campaigns` module.
- `src/features/leads/` — `campaign` on a lead, the form field, the Edit patch, the list filter in the URL and the API, and the name on the lead page.
- `src/features/lead-capture/` — the linked campaign on a QR code and its form.
- `src/features/orders/` — the lead lists they open pass `campaign: null`.
- `src/mocks/` — four campaigns, some leads tagged, the five endpoints, the campaign on leads and QR codes, and leads from a linked code.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — MKT-005, MKT-006.

## Tests

- `src/features/campaigns/components/campaigns.test.tsx` — 11 tests:
  - contract: `[MKT-005] Campaigns`, `[MKT-006] A campaign on a lead`;
  - screens: `[MKT-005] CampaignsPage`, `[MKT-006] The campaign on a lead`.
- The lead, QR code and order suites still pass with the new fields.
- By hand:
  1. As Admin, open Channel → Campaigns, add one, open the fair and try to delete it.
  2. Open a lead from See its leads and change its campaign under Edit.
  3. Link a campaign on a QR code.
