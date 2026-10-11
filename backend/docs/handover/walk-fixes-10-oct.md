# Walk fixes, 10 Oct: what changed for the frontend

These are the backend fixes for walk findings F-4, F-6, F-7, F-8, F-9, F-15 and R-12. The generated API docs (`backend/docs/api/`) are the record. This page says what to change on screen.

## Changed responses

| Endpoint | Before | Now | Screen change |
|---|---|---|---|
| `GET /approvals/thresholds` | `200` with an empty list for a dealer | `403` for anyone who is not staff | Route-guard `/approval-limits` to staff. Don't show "No approval limits are set" to a dealer. |
| `POST /lead-qr-codes`, `PATCH /lead-qr-codes/{id}` | `422` with `fields.partner_id` or `fields.body` = "staff only" for a dealer | `403` | A dealer sees his codes on `/qr-codes` read-only: hide New QR code, Edit and Switch off. |
| `GET /leads`, `GET /leads/stats`, `GET /leads/export` | Deleted leads included for a caller with `leads.delete` | Left out. New query `deleted=true` returns only deleted leads | The sidebar count and the dashboard stages now agree. A "Deleted leads" view, if you build one, passes `deleted=true`. |
| `GET /lookups/partners?q=` | Matched the firm name, code and contact person | Also matches a partner user's name: `q=Bhavesh` finds Shah Irrigation | Clear the "No channel partner" placeholder text before sending `q`. It was being sent as `q=No+channel+partnerBhavesh`. |
| Lead `score` | Two decimals (27.5) | A whole number, sent as `"28.00"` | Show it without decimals. |

## Changed behaviour, no contract change

- **The lead's channel partner reaches its drafts.** When `POST /leads/{id}/assign` changes `assigned_partner_id`, every draft quotation on the lead takes the new partner and is re-priced at its tier. Refetch open drafts after an assign. A sent quotation keeps the partner it was sent with.
- **A closed lead's score no longer moves.** Marking a lead lost used to raise it. Reopening scores it again.
- **A QR or website lead with only a district gets an owner.** It goes to the field officer with the fewest open leads in that district. It stays unassigned only when the district has no field officer.
- **The quotation and order PDFs** now have the Polysil logo, the rupee sign on every line amount, and the customer mobile as `+91 98765 43210`. Phone, email, website, company profile, bank details and signature are not printed yet. They wait on the client.

## Still the frontend's, from the same walk

- Route guards for `/approval-limits`, `/qr-codes` and `/dispatch` for a dealer (F-8).
- The partner box's placeholder text (F-9).
