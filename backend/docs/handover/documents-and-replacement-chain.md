# Documents on records, and the replacement order's approvers

Two changes from the client's sheet of 10 Oct. Full contracts: `docs/api/documents.md` and `docs/api/orders.md`.

## Documents (sheet item 3)

The client handles payments, purchase orders and paperwork outside the app, and wants each document attached to its record so a lead's whole story is in one place.

| Call | What it does |
|---|---|
| `GET /documents/types` | the type list with labels: purchase order, payment slip, signed quotation, invoice, delivery challan, transport receipt, site photo, land record, subsidy document, other. `needs_name` is true for other. Build the picker from this |
| `POST /documents` (multipart) | `record_type` (lead, quotation, sales_order, dispatch, payment), `record_id`, `doc_type`, `name` (required for other, a note otherwise), `file` (JPEG, PNG, WebP, HEIC or PDF, 10 MB). `201`; the same file with the same type again `200` |
| `GET /documents?record_type=&record_id=` | the documents on one record, newest first |
| `GET /leads/{id}/documents` | everything on the lead and on what came from it; each row has `record_type` and `record_label` (the quote, order or dispatch number) |
| `GET /documents/{id}/link` | a ten-minute link; never fetch it with the bearer token |
| `DELETE /documents/{id}` | the uploader, or staff who may add to the record. `204` |

Errors: `403` when you can see the record but may not add; `404` when you cannot see it; `409 record_closed` on a deleted or merged lead or a voided dispatch; `422 too_many_documents` past 50.

**Screens:** a Documents card on the lead, quotation, order and dispatch pages, with the list, an upload (type picker, a name box for Other), open and delete. On the lead page, show which record each document sits on. `preview` false (HEIC): offer a download instead of an image.

Who adds: leads and orders, whoever edits them (dealers on their own); quotations, staff only; dispatches, Dispatch or the order's editor; payments, Accounts.

## The replacement order's approvers (sheet item 12)

A free replacement order made from a complaint now waits on the State Manager, then the Regional Manager, then the MD, then Dispatch (was Dispatch alone). Nothing to build: the order page and the inbox show any chain. The list before Dispatch is a new setting, `replacement_approval_roles`, shown in Settings.
