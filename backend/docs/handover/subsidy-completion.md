# Subsidy completion: the farmer's share, supply date, bells, reopen

Full contracts: `docs/api/orders.md`, `docs/api/payments.md`, `docs/api/portal.md`, `docs/api/subsidy-applications.md`, `docs/api/notifications.md`, `docs/api/subsidy.md`. Everything here is additive. No field changes shape.

## 1. A subsidised order is paid by the farmer's share

On a subsidised order these numbers now use the farmer's share instead of the full total:

- `payable` on `GET /orders/{id}`
- the `payments` block (payable, balance, status, overdue)
- the orders list and approvals inbox payment status
- the dealer ledger's order row
- the farmer portal's order `total`

**Screen:** beside the payable on a subsidised order, label it "Farmer's share". The order total and the lines stay as they are. The approver's WhatsApp still shows the full total, because approval follows the full total.

The farmer's share is the farmer payable typed in. When it is blank, it is the material amount less the subsidy. When the material amount is blank too, it is the order total less the subsidy. It is never below 0 or above the order total.

## 2. The dispatch date on a subsidy application

`GET /subsidy-applications/{id}` and the list have a new field:

| Field | Meaning |
|---|---|
| `dispatched_on` | the date (IST) of the first dispatch of a subsidised order that names this application's lead. `null` until one is dispatched |

On the stage 7 ("Farmer share detail") form:

- Show `dispatched_on` beside the supply date, as "Dispatched on".
- **Do not send the `supply` key unless the user typed a date or cleared the field.** When the key is absent, the backend fills it from `dispatched_on`. Sending `"supply": null` clears it on purpose.

The supply report and the ageing report count a dispatched file as supplied even before stage 7 has a supply date.

## 3. New bell notifications

Six new `kind` values, all with `resource.type` = `subsidy_application` and `resource.id` = the application id. Open the application detail.

| kind | Title example |
|---|---|
| `subsidy_returned` | Subsidy file GJ/... was sent back to the field |
| `subsidy_query` | Subsidy file GJ/... has a query from the department |
| `subsidy_tr_failed` | Subsidy file GJ/... failed the trial run |
| `subsidy_closed` | Subsidy file GJ/... is closed |
| `subsidy_cancelled` | Subsidy file GJ/... was cancelled (body: the reason) |
| `subsidy_reopened` | Subsidy file GJ/... was reopened (body: the reason) |

They go to the file's owner and the lead's owner, never to the person who did it.

## 4. Reopen a closed file

`POST /subsidy-applications/{id}/reopen` with `Idempotency-Key`:

```json
{ "reason": "FP date entered wrong" }
```

- Who: admin sales and the MD (`subsidy.approve`). Show a **Reopen** button on a closed file for them only.
- Ask for a reason (1 to 500 characters).
- Returns the application, now `open`. Stages and values stay.
- `409 application_not_closed`: the file is open or cancelled. A cancelled lead gets a new application instead.
- `409 commission_settled`: the dealer's commission on this file is approved or paid.

After a reopen, the file closes again only when an entry writes a stage-16 amount or a stage-17 date. Say so in a hint under the button: "It closes again when the payment entries are complete."

## 5. Sprinkler areas between table steps

`POST /subsidy/calculate` for sprinkler now accepts an area between two table steps, for example 1.1 Ha. It was refused before.

- Quantities are those of the next step up.
- The unit cost is pro rata between the two steps.
- The result carries a warning starting `area_between_steps`. Show it in plain words: "The area is between table steps. Quantities use the next step; the unit cost is in between."
- Below 0.4 Ha or above 5 Ha is still refused with `exact_area_match_required`.
