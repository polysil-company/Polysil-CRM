# List exports to Excel

> A "Download" button on eight list screens. One new endpoint beside each list. Nothing else changes.

## The endpoints

| Screen | Endpoint |
|---|---|
| Leads | `GET /api/v1/leads/export` |
| Quotations | `GET /api/v1/quotations/export` |
| Orders | `GET /api/v1/orders/export` |
| Complaints | `GET /api/v1/complaints/export` |
| Tasks | `GET /api/v1/tasks/export` |
| Subsidy applications | `GET /api/v1/subsidy-applications/export` |
| Partners | `GET /api/v1/partners/export` |
| Users | `GET /api/v1/users/export` |

Each takes **the same query parameters as its list**, with the same names, minus
`limit`, `cursor` and `include_total`. Pass the filters the screen is showing.

## Calling it

A plain link cannot carry the bearer token, so fetch the file and save the blob:

```ts
const res = await fetch(`${API}/leads/export?${params}`, {
  headers: { Authorization: `Bearer ${token}` },
});
if (res.ok) {
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1]
    ?? "export.xlsx";
  saveAs(blob, name);            // or an <a download> on URL.createObjectURL(blob)
} else {
  const { error } = await res.json();   // the usual error envelope
  toast(error.message);
}
```

## What comes back

```
200
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="leads-2026-10-03.xlsx"
```

- The rows are exactly what the list shows for those filters, every page, and nothing
  outside the user's scope. A field officer gets their own leads.
- An empty list gives a file with the header row only. Not an error.

| Status | `error.code` | Show |
|---|---|---|
| 422 | `export_too_large` | the message ("more than 5000 rows, narrow the filters"); keep the filters |
| 422 | `filter_not_exportable` | complaints only, when `awaiting=me` is set: hide the button on the approvals queue |
| 422 | `validation_failed` | a bad filter, same as the list |
| 403 | | the user cannot see this list; hide the button |

## The button

- Put it in the list toolbar, beside the filters.
- Disable it while the request runs. A large export takes a few seconds.
- Partner users see it on the lists they have (leads, quotations, orders, complaints).

## Not in this change

CSV, PDF, and the client's own layouts. Those wait on the client (questions 13.7, 13.8).
