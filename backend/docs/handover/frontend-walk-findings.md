# Frontend walk on staging: what the frontend can pick up

A walk through https://polysil.pranayx.tech as the field officer and the district manager found the items below. The backend side is fixed or on its way. These are the frontend's, each with what the backend already sends.

## 1 · The approver cannot decide a discount (APPR-001)

- **Seen:** `/approvals` lists a quotation's discount request, but has only "Open the quotation". The quotation page shows a disabled "Waiting for approval" button. There is no Approve or Return.
- **Backend:** the discount step is an ordinary row of `GET /approvals/pending`, with `doc_type: "quotation"`. It is decided like an order step: `POST /approvals/steps/{step_id}/decision` with `{ "decision": "approve" | "reject", "remark": "..." }`. The answer is a `DecisionResult`, discriminated by `doc_type`. See `backend/docs/api/approvals.md`.
- **Ask:** Approve and Return buttons on the approvals row, and on the quotation page when the viewer is the approver. The pending row's `role` says whose step it is.

## 2 · No Approvals link in the sidebar

- **Seen:** `/approvals` works only by typing the URL.
- **Ask:** a sidebar entry for anyone whose role can decide something. `GET /approvals/pending` answers an empty list for a role that decides nothing.

## 3 · The lead history can say more (LEAD-005)

- **Seen:** "Asha Patel changed the channel partner", without saying which partner.
- **Backend:** since this week, every `lead.assigned` event carries a name beside each id:
  - `owner_name` beside `owner_user_id`;
  - `partner_name` beside `assigned_partner_id`;
  - `previous_owner_name` beside `previous_owner_user_id`, on a handover.
  Every `quotation.*` event carries `quotation_id`, `quote_no` and `version`. `quote_no` is null on a draft, so show "draft" and link by `quotation_id`.
- **Ask:** "Assigned to Ravi Joshi", "Channel partner set to Shah Irrigation, Rajkot", "Quotation QT/GJ/2026-27/00003 v2 sent", with a link.
- **Fixed on the backend:** the history showed "Polysil" as the one who asked for a discount. Events written inside the database carried no actor name. The timeline now names the actor for staff readers (migration 022). No frontend change is needed.

## 4 · A draft waiting for approval is listed as "Draft"

- **Seen:** the Quotations list shows "Draft" for a draft whose discount is waiting for approval. Only the quotation page shows the waiting state.
- **Backend:** list rows now carry `awaiting_approval` (true while a discount request waits). The full quotation also has `discount.send_gate`, which is `pending` then.
- **Ask:** show "Awaiting approval" in the list when `awaiting_approval` is true.

## 5 · The dashboard, the bell and Messages

- **Dashboard:** `GET /dashboard/overview` is on staging now; it answered 404 during the walk because it was not deployed yet. Reload. The shape is in `backend/docs/api/dashboard.md`. It is snake_case, and every figure is a decimal string.
- **Bell:** `GET /notifications` and `POST /notifications/read` are being built (BE-009). They follow your proposed shape.
- **Messages:** not started (BE-010).

## 6 · Seen twice in the partner picker

"Saurashtra Agro Distributors" appears twice. These are two real records from two seed scripts. The demo seed now names its own "Rajkot Agro Distributors". Staging keeps both rows until the next reseed.
