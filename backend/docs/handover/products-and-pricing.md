# Products, prices and tax: what the frontend needs

The catalogue, the price lists and the commercial tax engine are built and the
ten endpoints are live. The generated contract is `backend/docs/api/products.md`
and `backend/docs/api/pricing.md`, which is the record; this document is the
context around it.

---

## The three screens this implies

**The product picker.** `GET /products` with `q`, `category`,
`quotation_category` and `active`. Offset-paged with a total, unlike the lead
list, because the catalogue is a fixed 1,092 rows and a picker wants to show how
many matched.

**The catalogue screen.** The same rows, editable by an administrator, plus the
two dated facts each product carries: its tariff heading and, through that, its
tax slab.

**The rate sheet.** A price list and, beside every product, the rate that list
holds for it. Most of them are empty when a list is new, and filling them in is
the whole job.

---

## Money and quantities are decimal strings

`"1857.42"`, never `1857.42`. Do not parse them into a JavaScript number and
back. A float cannot hold a rupee figure exactly, and these quotations have to
match the client's own spreadsheets to the paisa.

The same goes for quantities: `"18.000"` on a unit that takes three decimals,
`"18"` on one that takes none.

---

## Pricing a set of lines

```http
POST /api/v1/pricing/quote-lines
{
  "place_of_supply_territory_id": "uuid",
  "lines": [ { "product_id": "uuid", "qty": "18", "discount_pct": "0" } ]
}
```

**Nothing is stored and nothing is locked.** Call it as the user types,
debounced, exactly like the subsidy calculator. It takes no `Idempotency-Key`.

### Send where the goods are going, not where the dealer is

`place_of_supply_territory_id` is the **ship-to**. It decides which tax applies:
delivery inside the seller's own state splits into CGST and SGST, delivery to
another state is IGST. Sending the dealer's own territory instead is the mistake
that under-collects tax on an inter-state order, and the difference is a credit
note rather than a rounding argument.

### Do not do the arithmetic

Every printed figure comes back, in the order an invoice prints it:

```jsonc
{ "rate": "103.19", "qty": "18",
  "gross": "1857.42", "discount": "0.00", "taxable": "1857.42",
  "hsn_code": "3917", "gst_slab": "5.000",
  "cgst_rate": "2.500", "sgst_rate": "2.500", "igst_rate": "0.000",
  "cgst": "46.44", "sgst": "46.44", "igst": "0.00",
  "total": "1950.30" }
```

`gross` is returned so nobody re-derives `rate × qty` and lands on a different
paisa. `cgst_rate` and `sgst_rate` are returned so nobody halves the slab in
JavaScript. `intra_state` is returned so the document does not re-derive which
tax applies. Print what you are given.

**Rates carry three decimals; money carries two.** That is not a typo. Half of
the 0.25 % slab is 0.125, and at two decimals it prints as 0.13 - two halves
summing to 0.26 against a slab of 0.25. So `gst_slab`, `cgst_rate`, `sgst_rate`
and `igst_rate` are `"5.000"` and `"2.500"`, while `gross`, `cgst` and `total`
stay `"1857.42"`.

### Two things that look like bugs and are not

**CGST always equals SGST.** Each is computed at half the slab and rounded on its
own, which is what the client's own workbooks do.

**A small intra-state line carries a paisa more tax than the same value would
inter-state.** Taxable 1.00 at 5 % gives 0.03 + 0.03 = 0.06 against IGST 0.05.
That is correct under per-component rounding.

### Keep two ids on every line

`price_list_item_id` and `gst_rate_id`. When quotations land, saving one
re-resolves the price and compares these; if either moved between the preview and
the save you will get a `rate_changed` or `tax_rate_changed` warning rather than
a silent reprice. Keeping them costs nothing now and is how that works later.

---

## Read the warnings

Each is one string shaped `code: sentence`. Split on the first colon, switch on
the code, show the sentence.

| code | what it means |
|---|---|
| `provisional_pricing` | some figures on this quotation are our stand-ins, not the client's. **Show the badge.** Fine for testing, not for a quotation anyone sends |
| `future_price_date` | you asked for a date ahead of today, so these are the rates that will be in force then |
| `mixed_price_lists` | the lines drew from more than one price list. Right if a state list is a discount layer over the base, a mispricing if it replaces it, and nobody has told us which yet |

---

## `provisional_fields`, per field

On a product row and on every priced line. It names which commercials are still
our stand-ins rather than the client's: `hsn_code`, `gst_slab`, `mrp`,
`pack_multiple` on a product; `rate` and `gst_slab` on a line.

An empty list means every figure on that row is the client's own. A non-empty one
is not an error — it is the state of the data until they send the real file.
**Show it per field**, not as one badge on the row: a product can have a
confirmed pack multiple and a guessed tax slab at the same time.

---

## Quantities are checked against the unit

Three ways a quantity is refused, all `422` naming `lines[n].qty`:

- more decimals than the unit admits. A `NOS.` item cannot be ordered 1.5 of;
  the product row tells you with `uom_decimals`
- not a multiple of `pack_multiple`, when the product sets one
- zero, below zero, or above 1,000,000

Read `uom_decimals` and `pack_multiple` off the product and enforce them in the
input, so the user finds out while typing rather than on submit.

---

## Price lists, and why publishing is a separate step

A list is **drafted**, filled, then **published**. Nothing it holds affects a
quotation until it is published, so a list can be built over weeks.

```
POST   /price-lists              -> a draft
PUT    /price-lists/{id}/items   -> set the rates, draft only, replaces them all
POST   /price-lists/{id}/publish -> in force
```

Three things to build for:

**`unpriced_count` is on every list row.** It is how many active products the
list holds no rate for, and it is what publishing refuses on. Show it on the
editing screen, not at publish time.

**Publishing refuses a half-filled list** with `409 price_list_unpriced` and the
count. Offer `allow_unpriced: true` as a deliberate choice, not a retry: it is
the normal case for a state list that corrects a few rates, and the wrong answer
for a list meant to replace the base.

**A published list's rates never change.** `PUT /items` on one is a `409
price_list_published`. A correction is a new list effective from the day the new
rates start — the UI should offer "create a new list from this one", never an
edit. This is not a policy we can relax: editing rates in place would restate
every order already priced from them.

The only thing that moves on a published list is `effective_to`, forward only.

---

## A dealer sees less, and that is correct

A partner signed in through the portal reads the base price list and their own
tier's, and never a tier above them. A dealer cannot see distributor rates. That
is enforced in the database, so a list that looks short for a dealer and long for
an administrator is working.

A partner also prices only for themselves: `partner_id` in the body is refused
for a partner and is there for staff quoting on a partner's behalf.

---

## What is still a stand-in

Every price and every tax code on the development box is ours. The client will
send the real product master, prices and HSN codes later; until then the figures
are realistic rather than right, and the API says so on every response that uses
one.

Two more things are deliberate gaps rather than oversights, both visible in the
data:

- the seller's GST registration is a single default one, because warehouses do
  not exist yet. A quotation always taxes from the same registration
- 111 of the 1,092 products are marked usable in either block of a subsidy
  quotation, so the head-versus-field check has nothing to say about them
