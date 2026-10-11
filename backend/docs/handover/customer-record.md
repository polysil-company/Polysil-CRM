# Customer record

> Full spec: FS-041. All additive.

A lead that reaches **qualified** gets a customer, found by mobile number or made new. Later leads from the same number join it. Leads already past qualified were linked when the backend was deployed.

The Lead now has `customer_id` (null until qualified). Show a "Customer" link when it is set.

## Find a customer

```jsonc
// GET /api/v1/customers?q=ramesh&territory_id=<id>&limit=50&cursor=     needs leads view
{ "data": [ {
    "id": "uuid", "customer_type": "farmer", "name": "Rameshbhai Patel", "mobile": "+919876543210",
    "email": null, "territory": { "id": "uuid", "name": "Vadod", "level": "village" },
    "village": "Vadod", "address": null, "survey_no": null,
    "consent_given_at": null, "consent_channel": null,
    "lead_count": 2, "created_at": "...", "updated_at": "..." } ],
  "meta": { "limit": 50, "next_cursor": null } }
```

- `q` is a name or mobile, at least 3 characters.
- You see a customer when you can see one of its leads.

## The customer page

`GET /api/v1/customers/{id}` returns the customer plus:

```jsonc
"leads":      [ { "id", "inquiry_no", "stage", "source", "campaign_name", "created_at" } ],
"quotations": [ { "id", "quote_no", "status", "total", "lead_id", "sent_at" } ],
"orders":     [ { "id", "order_no", "status", "total", "lead_id", "submitted_at" } ]
```

Only what you can see, newest first, at most 100 each. `404` if you can see none of its leads.

## The timeline

`GET /api/v1/customers/{id}/timeline?limit=50&before=<next_cursor>`

- Each entry is a lead timeline entry, plus `lead_id` and `inquiry_no`.
- The customer's own events (`customer.created`, `customer.updated`) have `lead_id: null`.
- The same payloads and rules as the lead timeline.

## Edit (staff with leads edit; a dealer gets 403)

`PATCH /api/v1/customers/{id}` with `Idempotency-Key`:
- `customer_type` (farmer, institution, company), `name`, `email`, `territory_id`, `village`, `address`, `survey_no`.
- `consent_given: true` with `consent_channel` (whatsapp, form, verbal, written) records consent now. Sending it again unchanged keeps the first date. `consent_given: false` withdraws it.
- The mobile cannot be changed here.
- Editing never changes the leads, quotations or orders.

## Screens

1. Customer page: the details card with Edit and a consent switch; leads (with source and campaign), quotations, orders; the timeline.
2. Customer search: name or mobile, and an area filter.
3. Lead detail: a link to the customer.
