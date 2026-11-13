# Ratings

> Staff record a farmer's star rating of an installation, a service visit or a product; a dealer rates Polysil the same way; every dealer has a derived rating from how fast it pays and how much it orders. Full spec: FS-043. Built: the generated API doc `ratings.md` is the record.

## Feedback ratings

```jsonc
// POST /api/v1/ratings                         Idempotency-Key
{ "target": "installation",                    // installation | service | product
  "sales_order_id": "uuid",                    // installation and product
  "complaint_id": null,                        // service
  "product_id": null,                          // product: shipped on that order
  "score": 4,                                  // 1 to 5
  "comment": "Drippers clogged in week two." } // optional, up to 1000
// rated_by is set for you: staff record the farmer's ("customer"), a dealer's user its own ("dealer")

// 201
{ "data": { "id": "uuid", "target": "installation", "score": 4, "comment": "...",
            "rated_by": "customer", "entered_by": { "id": "uuid", "full_name": "..." },
            "partner": { "id": "uuid", "name": "Shah Irrigation", "partner_type": "dealer" },
            "lead": { "id": "uuid", "inquiry_no": "..." },
            "order": { "id": "uuid", "number": "SO/GJ/2026-27/00012", "status": "dispatched" },
            "complaint": null, "product": null, "created_at": "..." } }
```

| Code | Status | Show |
|---|---|---|
| `not_rateable` | 422 | "Nothing has shipped yet" / "The complaint is not closed" |
| `product_not_shipped` | 422 | the product has not shipped on this order |
| `rating_exists` | 409 | already rated; hide the button |
| `not_your_order` | 403 | a dealer on a sub-dealer's or another dealer's document |

**When to show the buttons:**
- **Rate installation** on an order with at least one dispatch.
- **Rate product** on each line with something shipped.
- **Rate service** on a closed complaint.

Hide each one once `GET /ratings?sales_order_id=` (or `complaint_id=`) shows a rating by the caller's kind.

**A dealer's view of a farmer's rating:** the score only. `comment` and `entered_by` are `null`, and the timeline event has no actor. Show "Customer rating: 2 stars".

## Lists

- `GET /api/v1/ratings?target=&partner_id=&product_id=&lead_id=&sales_order_id=&complaint_id=&from=&to=&max_score=&limit=&cursor=`. Newest first. `max_score=2` is the "unhappy customers" view.
- `GET /api/v1/ratings/summary?group_by=partner|product|target&from=&to=` returns `[{ key: {id, name}, count, average, low }]`, lowest average first.

## The dealer card

```jsonc
// GET /api/v1/partners/{id}/dealer-rating
{ "data": { "partner_id": "uuid", "on": "2026-10-09", "window_days": 365,
  "orders": 23, "paid_orders": 19, "payment_days": "18.4", "payment_score": 3,
  "order_value": "1240000.00", "value_score": 4, "rating": "3.5",
  "feedback": { "count": 6, "average": "4.33" } } }
// 403 rating_not_permitted: the caller does not see payments (field officers, intake)
```

- **Who sees it:** Accounts, managers who see payments, and the dealer itself. Hide the card on a 403.
- **When a figure is `null`:** no order counts yet. Show "Not rated yet".
- **Footnote under the card:** "From days to full payment and order value over the last year. Feedback is shown apart."

## Settings

Three new rows in `GET /settings`:

| Key | Kind | Value |
|---|---|---|
| `dealer_rating_window_days` | int | days of orders counted |
| `dealer_rating_payment_days` | **bands** | `[7, 15, 30, 60]`: days at or under, scoring 5, 4, 3, 2 |
| `dealer_rating_order_value` | **bands** | `[100000, 500000, 1000000, 2500000]`: rupees at or over, scoring 2, 3, 4, 5 |

`bands` is a new kind: render four number inputs and send a list of four rising whole numbers. Anything else is 422.
