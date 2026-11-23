# Price lists by sale type

Full contract: `docs/api/pricing.md`. Additive; nothing existing breaks.

## What changed

A price list may now be for one sale type: commercial, industrial or subsidised. A quotation or order of that type takes its rates from that list first. A list with no sale type is general and prices every sale type, as before.

## Screens

1. **Price list form:** a "Sale type" select: "All sale types" (sends `null`, the default), "Commercial", "Industrial", "Subsidy" (sends `subsidised`). It cannot be changed after the list is created, so disable it on an existing list.

```
POST /price-lists
{ "name": "Subsidy rates Gujarat", "effective_from": "2026-10-15",
  "state_territory_id": "...", "channel_tier": null, "sales_type": "subsidised" }
```

2. **Price lists table:** a "Sale type" column (`sales_type` on every list; null shows "All") and a filter: `GET /price-lists?sales_type=commercial`, or `sales_type=general` for lists with no sale type.
3. **Quotation and order line editors:** send the document's sale type on the preview, so it shows the price the save will charge:

```
POST /pricing/quote-lines
{ ..., "sales_type": "commercial" }
```

   Send the quotation's `sales_type`, or the order's `order_type`, as it is. Any value is accepted; only commercial, industrial and subsidised have lists of their own.

4. **Quotation and order detail:** no change. `price_list` already names the list used.

## Refusals and messages

| Code | When | Say |
|---|---|---|
| `422 type_mismatch` on `POST /orders` from quotations | an industrial order from a commercial quotation, or the reverse | "This quotation is commercial. Make a commercial order, or revise the quotation." |
| `409 rate_changed` on send or submit | a typed list was published since the draft was saved | "Prices changed. Save again to update, then send." |
| `422 product_not_priced` | no list prices the product for this sale type | as today |
