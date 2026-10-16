# Subsidised orders, the dealership enquiry, and GSTIN details

Full contracts: `docs/api/orders.md`, `docs/api/leads.md`, `docs/api/dealer-applications.md`. Everything here is additive.

## Subsidised orders (sheet item 15)

A subsidy sale entered without a quotation, for one farmer's lead or several. Staff only.

### New order screen, type Subsidised

Show the usual direct order fields (party, place of supply, lines from the price list), **no single lead picker**, and instead:

| Field | Notes |
|---|---|
| Leads | a multi-picker, 1 to 50, qualified or later. The first one picked is the order's lead: say so on screen. It cannot change later |
| Material amount | optional. Empty means "the order total" and follows the lines |
| Subsidy | required |
| Farmer payable | optional. Empty means material less subsidy. Show that figure as a hint |

`POST /orders`:

```json
{ "order_type": "subsidised", "party": {...}, "place_of_supply_territory_id": "...",
  "lines": [...],
  "subsidy": { "lead_ids": ["...", "..."], "material_amount": "245000.00",
               "subsidy_amount": "196000.00", "farmer_payable": "49000.00" } }
```

Do not send `lead_id` on a subsidised order (`422 lead_from_subsidy`).

### Order page

`subsidy` on `GET /orders/{id}` (null on other types):

```json
{ "material_amount": "245000.00", "subsidy_amount": "196000.00", "farmer_payable": "49000.00",
  "material_is_total": false, "farmer_payable_is_derived": false,
  "leads": [{"id": "...", "inquiry_no": "POL/..."}] }
```

- Show the three amounts and the leads. A lead with `inquiry_no: null` is one you cannot see: show "a lead you cannot see".
- When `material_is_total`, label it "Order total". When `farmer_payable_is_derived`, label it "Material less subsidy".
- `warnings` may hold `subsidy_above_material` (after a lines edit) or `farmer_payable_not_material_less_subsidy`. Show them on the draft.
- The order's top-level `payable` is the total less scheme benefits. It is **not** the farmer's share.
- Documents card: the quotation copy (`signed_quotation`) and the payment slip (`payment_proof`), with `POST /documents` and `record_type: sales_order`.

### Editing

`PUT /orders/{id}/subsidy` with the same block, while the order is a draft (also after an amend). Keep the first lead first: `422 first_lead_fixed` otherwise. The order type cannot be changed to or from subsidised (`422 order_type_fixed`).

Errors to show: `lead_not_visible`, `lead_not_open` (`fields` names the lead under `subsidy.lead_ids`), `subsidy_above_material`, `payable_above_material`, `subsidy_missing`, `subsidy_not_allowed`, `order_type_not_subsidised`, `409 order_not_draft`.

## The dealership enquiry type

- Leads take `inquiry_type: "dealership"`. Add it to the type picker as "Dealership".
- A dealership lead can go from qualified straight to won, without a quotation.
- The transition that wins it answers `dealer_application: {id, apply_url, not_started}`. When `apply_url` is set, show it once with Copy and Share on WhatsApp, as on the dealer application screen. When `not_started` is `mobile_in_use` or `application_open`, say no application was started and why.

## GSTIN details

`GET /gstin/{gstin}` and the applicant's `GET /public/dealer-apply/{token}/gstin/{gstin}` now answer `lookup: "found"` with `legal_name`, `trade_name`, `address`, `status` once the server has a provider key. Prefill the names when found; keep the fields editable. `unavailable` or `not_found`: the applicant types them, as today.

## Amend after a voided dispatch

`POST /orders/{id}/amend` answers `409 voided_dispatch_holds_lines` when a dispatch on the order was voided. Say "This order had a dispatch voided. Cancel it and create a new one."
