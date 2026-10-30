---
date: 2026-09-30
type: feature
title: "Approval limits: an order's value and a quotation's discount per role,
  changed by an administrator"
dataIds:
  - APPR-002
author: Nakul Srivastava
breaking: false
---

## Before

The approval limits lived only in the backend's seed: District approves orders up to ₹1,00,000 and State up to ₹5,00,000 including GST, and discounts go from a field officer's 5 % up to Regional's 20 %. Nobody could see them in the app, and changing one needed a database change. The mock hard-coded the same bands.

## Now

**Approval limits (APPR-002)** — `/approval-limits`, under Admin for roles with `masters`:

- **Two ladders**, lowest level first:
  - **Order value**, including GST: District, State and Regional Manager ("Up to ₹1,00,000", "No limit"), saying that a bigger order goes on to the next level, then to Accounts and Dispatch.
  - **Discount on a quotation:** the field officer's own limit, then District, State, Regional and Admin-Sales.
- **A territory's own limits** show under the company-wide ladder, marked "Own limits"; levels it doesn't set use the company-wide limit.
- **Changing one level** (`masters.edit`, Admin in the mock) opens a dialog:
  - it shows the current limit and what it means for that level;
  - it gives the bounds in words ("Above ₹1,00,000, to keep each level above the one below");
  - **No limit** is offered only at the top of a ladder;
  - a limit out of order is refused on the field before it is sent.
  - Saving shows the new ladder at once and says it applies from the next order or discount request.
  - If the backend refuses because someone changed another level meanwhile (`thresholds_not_increasing`), the dialog says so and the ladders reload.
- **Everyone else** reads the limits, with "Only an administrator changes these".
- **States:** skeleton, a warning when no limits are set, errors with retry.

**The mock** keeps the limits as rows, as the backend does, with one district's own order limit as an example. `PUT` follows the backend's rules:

- only `masters.edit` may change a limit;
- the levels must stay in order;
- only Admin-Sales may have no discount limit;
- an order limit must be above 0, and a discount at most 100.

A changed limit now decides the next order's chain and the next discount's approver in the mock.

## Discussion

- **Read by all, changed by administrators:** `GET /approvals/thresholds` is open to anyone signed in, so managers can see where their authority stops; `PUT` needs `masters.edit`, so the page sits under Admin with the `masters` module.
- **No new territory override from this screen yet.** It edits the rows that exist, company-wide and per territory. Adding a territory's own limit needs a territory picker; `TODO(APPR-002)` when the client asks for it.
- **The client's real figures are still owed** (BE-014). This screen lets an administrator enter them once they come, with no backend change.
- **Axe on a phone:** a read-only page with nothing focusable in the scrolling `<main>` trips `scrollable-region-focusable`. The app shell's `main` is `tabIndex={-1}` on purpose (skip link target). Left as is; worth a look in the shell later.
- **Also here:** the direct order builder (SO-005) is registered and planned, not built. It follows the backend pick-ups (BE-001…017), which matter more day to day.

## Files changed

- `src/features/approvals/api/` — thresholds contract (`Threshold`, `ThresholdPutRequest`, the limit form), `getApprovalThresholds`, `putApprovalThreshold`, `approvalThresholdsQueryOptions`, `usePutApprovalThreshold`
- `src/features/approvals/lib/approval-limits.ts` — ladders, bounds, who may have no limit, refusals; `approval-labels.ts` — `limitRoleLabel`
- `src/features/approvals/components/approval-limits.tsx`, `approval-limit-dialog.tsx` — new
- `src/app/(app)/approval-limits/page.tsx`, `loading.tsx` — new route; `src/components/layout/navigation.ts` — Approval limits under Admin
- `src/mocks/data/approvals.ts` — `seedThresholds`, `limitOf`, `orderManagersFor`, `quotationApproverFor` from the rows; `data/orders.ts` — the chain from the limits; `handlers/approvals.ts` — `GET`/`PUT /approvals/thresholds`; `handlers/orders.ts`, `handlers/quotations.ts`, `db.ts` — read the limits
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — APPR-002 in progress, SO-005 planned
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/approvals/limits-*`
- `e2e/smoke.spec.ts` — the limits as Admin, with axe

## Tests

- `src/features/approvals/lib/approval-limits.test.ts` — `[APPR-002]` ladders company-wide and per territory, bounds and their words, only the top without a limit, formatting
- `src/features/approvals/api/approval-limits.test.ts` — `[APPR-002]` reading the rows; an administrator's change, `thresholds_not_increasing`, no discount limit below Admin-Sales, a discount over 100; refused without `masters.edit`
- `src/features/approvals/components/approval-limits.test.tsx` — `[APPR-002]` read-only for a manager; an administrator's change refused out of order, then saved
- `e2e/smoke.spec.ts` — `[APPR-002]` both ladders and the dialog as Admin; axe finds no violations; desktop and phone
- By hand (`npm run dev`, Preview as role → Admin): open Admin → Approval limits; change State Manager's order limit to ₹50,000 (refused on the field), then ₹4,00,000. As State Manager: read-only. Light and dark, 360px and desktop.
