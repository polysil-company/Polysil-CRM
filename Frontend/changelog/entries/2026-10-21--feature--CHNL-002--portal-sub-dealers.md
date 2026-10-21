---
date: 2026-10-21
type: feature
title: Dealers add their own sub-dealers
dataIds:
  - CHNL-002
  - CHNL-001
author: Nakul Srivastava
breaking: false
---

## Before

Channel partners was staff only. The backend already lets a distributor or dealer on the portal add the next type down under itself (`partners.md`), but the screens waited on the client's answer.

## Now

The client decided on 20 Oct: dealers add their own sub-dealers. The backend's rule covers distributors too, who add their dealers.

**Channel partners for partner users**

- The menu item now shows to whoever may view partners. Per RBAC.md §6.3, that is a distributor or a dealer; a sub-dealer has no partners grant and never sees it.
- The list is the backend's scope: the user's own business and the partners under it.
- **Add a sub-dealer** for a dealer, **Add a dealer** for a distributor. There is no New partner or Excel import, which stay staff only.
- **Dealer applications** (recruitment) stays staff only. The tab is hidden from partner users, and its address shows "You don't have access to this page".

**Adding one**

- The form always starts under the user's own business, whatever the address asks for.
- The type is fixed to the next one down, and "Under which dealer" (or distributor) is fixed to the user's business. Both show read-only.
- No credit terms: those are set by staff.
- On a partner's page, **Add a sub-dealer** shows only on the dealer's own page, never on a partner under it, because the backend refuses that.

**Mock**

- A distributor and a dealer get partners view, create and edit over their subtree, as RBAC.md §6.3 says; a sub-dealer gets none.
- The three demo partner users' own businesses are partner records:
  - Gujarat Agro Distributors at the top;
  - Shah Agro Traders under it;
  - Kisan Seva Kendra under that.
- The list, a partner, edits and the export are scoped to the caller's subtree.
- A partner user adding anywhere but under itself gets 422 on `parent_id`.

## Discussion

- **Distributors too.** The client's answer named dealers. The backend's rule is the same for a distributor and its dealers, and the screens follow the permissions, so a distributor gets **Add a dealer**. If the client wants dealers only, the backend removes `partners.create` from the distributor role and the button goes with it.
- **The new sub-dealer can't sign in yet.** Adding its people is in Users & roles, which is staff only. A dealer asks Polysil staff to add a login for the new sub-dealer.
- **Seed counts changed.** The staff partner list now has 12 partners, 11 open, so four tests' expected counts moved with it.

## Files changed

- `src/components/layout/navigation.ts`: Channel partners follows the `partners` permission, not staff only; `/partners/applications` is staff only.
- `src/features/partners/components/partners-tabs.tsx`: the tabs show to staff only.
- `src/features/partners/components/partners-list.tsx`: **Add a sub-dealer** or **Add a dealer** for partner users.
- `src/features/partners/components/partner-pages.tsx`: a partner user adds under its own business.
- `src/features/partners/components/partner-form.tsx`: type and parent read-only for partner users.
- `src/features/partners/components/partner-detail.tsx`: Add only on the user's own page.
- Mock:
  - `src/mocks/data/permissions.ts`: the grants;
  - `src/mocks/data/partner-scope.ts`: the demo businesses and the subtree;
  - `src/mocks/db.ts`: the businesses in the seed;
  - `src/mocks/handlers/partners.ts`: the scope and the portal rule.
- Tests: `partners-ui.test.tsx`, `partners.test.ts`, `navigation.test.ts`.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/partners/portal-*`.

## Tests

`src/features/partners/components/partners-ui.test.tsx`, 4 new tests in `[CHNL-002] On the portal: a dealer adds its own sub-dealers`:

- the dealer's own business and its sub-dealers, with **Add a sub-dealer**, and no New partner or import;
- a sub-dealer added under the dealer, with the type and dealer fixed and no credit terms, even when the address names another parent;
- **Add a dealer** for a distributor; 403 for a sub-dealer;
- **Add a sub-dealer** on the dealer's own page only.

`navigation.test.ts`: Channel partners opens to a dealer, but not to a sub-dealer; Dealer applications stays staff only.

To check by hand in the mock, choose Preview as role → Dealer, then:

1. Open **Channel partners** and select **Add a sub-dealer**.
2. Enter a code and a business name, and select **Add the partner**.
