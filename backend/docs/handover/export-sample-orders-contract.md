# Export and sample orders

> Staff can raise export quotations and orders, and sample orders. Two client questions are open (14.5 on export tax, 6.12 on samples), so each answer is an admin setting with a default. Full spec: FS-042. Built: the generated API docs (`orders.md`, `quotations.md`, `pricing.md`, `seller-gstins.md`) are the record.

## What changes for existing screens

- **Order form:** the type picker gains **Export** and **Sample**, for staff only. A dealer gets 403 `type_staff_only`.
  - **Export:** show a **Country** field (`export_country`, required) and hide the party GSTIN.
  - **Sample:** typed lines only, no "from quotations". Under free pricing every line comes back 100 % off and the total is 0.00. Show "Free sample" on each line.
- **Quotation form:** the sales type picker gains **Export**, with the same Country field. **Sample** stays refused.
- **Preview** (`POST /pricing/quote-lines`): send `tax_treatment` for an export, or the preview shows domestic tax. Use the treatment the document will get. For a new export, ask `GET /settings`: `export_tax_treatment` `lut` means `export_lut`, `igst` means `export_igst`.
- **Order and quotation detail:** show `tax_treatment`, `export_country`, `lut_arn` and, on a sample, `sample_pricing`.
- **Approvals inbox:** a sample's request amount is its list value, not its total. No change needed.
- **Admin › Settings:** three new settings appear in `GET /settings`. The screen already lists whatever comes back.

## New fields

```jsonc
// POST /api/v1/orders (and PATCH): new optional field
{ "order_type": "export", "export_country": "Kenya", "party": { "name": "Nairobi Agro Ltd", "mobile": "9876543210" }, ... }

// every order and quotation now carries
{ "tax_treatment": "export_lut",      // domestic | export_lut | export_igst; fixed at create
  "export_country": "Kenya",          // null unless export
  "lut_arn": "AD2404260012345",       // order: set at submit; quotation: at its price date
  "sample_pricing": "free" }          // orders only: free | charged | null
```

Under `export_lut` every line has `igst_rate` `"0.000"` and `igst` `"0.00"`. `gst_slab` still shows the product's slab. `intra_state` is always false on an export.

## New endpoints: seller GSTINs and LUTs

```jsonc
// GET /api/v1/seller-gstins                          products.view
{ "data": [ { "id": "uuid", "gstin": "24AAACP1234A1Z5", "legal_name": "...", "state_code": "GJ",
              "is_default": true, "is_active": true,
              "luts": [ { "id": "uuid", "arn": "AD2404260012345", "valid_from": "2026-04-01",
                          "valid_to": "2027-03-31", "in_use": true } ] } ] }   // newest year first

// POST /api/v1/seller-gstins/{id}/luts               products.edit, Idempotency-Key
{ "arn": "AD2404260012345", "valid_from": "2026-04-01", "valid_to": "2027-03-31" }
// 201: the LUT.  409 lut_overlap | lut_duplicate   422 lut_dates (crosses 31 March)

// DELETE /api/v1/seller-gstins/{id}/luts/{lut_id}    products.edit, Idempotency-Key
// 204.  409 lut_in_use (a document carries it: the delete button should hide when in_use)
```

Screen: **Admin › Seller GSTINs**: each registration with its LUTs by year. Add one; remove one that is not in use. No seeded role holds `products.edit`: an admin grants it first.

## Settings

| Key | Default | Allowed | Effect |
|---|---|---|---|
| `export_tax_treatment` | `lut` | `lut`, `igst` | new exports only |
| `sample_pricing` | `free` | `free`, `charged` | new samples only |
| `sample_max_value` | `50000` | 1 to 10,000,000 | list value; checked at create, edit and submit |

## Error codes

| Code | Status | Show |
|---|---|---|
| `lut_missing` | 422 | "No LUT covers this date. Ask an admin to record this year's LUT." |
| `export_country_required` | 422 | on the Country field |
| `export_party_gstin` | 422 | on the GSTIN field: an export buyer has none |
| `export_country_not_export` | 422 | a country sent on a non-export order |
| `sample_over_limit` | 422 | "A sample may be worth up to X at list price." |
| `sample_from_quotation` | 422 | samples are typed in |
| `type_mismatch` | 422 | an export order from non-export quotations, or the reverse |
| `order_type_fixed` | 422 | the type of an amended order, or one made from quotations, cannot change |
| `type_staff_only` | 403 | dealers cannot raise exports or samples |
