# In-app assistant

> Full spec: FS-045. All additive. A search box, not a chatbot.

## Search

`GET /api/v1/assistant?q=<text>&limit=8`: staff and dealers.

```jsonc
{ "data": {
  "actions": [ { "key": "quotation.create", "title": "New quotation",
                 "hint": "Start from a qualified lead", "screen": "quotations.new", "module": "quotations" } ],
  "records": [ { "kind": "lead", "id": "uuid", "label": "POL/GJ/2026-27/00123 · Rameshbhai Patel",
                 "screen": "leads.detail" } ] } }
```

- **Actions:** what the user may do, best match first. An empty `q` gives a starter set.
- **Records**, from 3 characters:
  - leads, and their customers, by number, by mobile (4 or more digits, any spelling) or by name (any script);
  - quotations, orders and complaints by number (`QT/`, `SO/`, any case, a prefix is enough), or by a serial alone (`123`).
- `kind` is `lead`, `customer`, `quotation`, `sales_order` or `complaint`, the same words as a notification's `resource.type`.
- `screen` is a stable key. Map it to your route and pass `id` for a record. The generated API doc lists every key.
- `q` over 100 characters or with control characters is `422`; `limit` is 1 to 20.

Debounce 250 ms and cancel the request in flight.

## Help page

`GET /api/v1/assistant/actions`: every action the user may take.

## Screens

1. A search box in the header (Ctrl+K), two groups: Actions and Records.
2. A help page from `/assistant/actions`.
