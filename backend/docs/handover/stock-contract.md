# Stock: warehouses, availability on the order form, the stock list

> **Status: built on the backend.** These shapes are what the API returns. They only gain fields from here.

Polysil's depots and warehouses now hold stock. The order form's "Order to" picks one. A dispatch takes stock out of the warehouse it left from. Availability is a warning on the order form; it never blocks an order. Dealers see no stock.

All paths are under `/api/v1`. Quantities are decimal strings in the product's unit. Every POST and PATCH takes `Idempotency-Key`.

## Who can do what

| Role | Reads | Records stock | Edits warehouses |
|---|---|---|---|
| Every staff role | yes | no | no |
| Dispatch manager | yes | yes | no |
| Admin, MD | yes | yes | yes |
| Dealers, the board | no (403) | no | no |

## The order form

- **"Order to"**: `GET /warehouses` (the default comes first). Send `warehouse_id` on `POST /orders` and `PATCH /orders/{id}`; null means the default. A dealer must not send it (422).
- **Per line:** `GET /stock/availability?warehouse_id=&product_ids=a,b,c` (up to 100):

```json
{ "data": { "warehouse_id": "uuid",
            "items": [ { "product_id": "uuid", "available": "850", "on_hand": "1250" } ] } }
```

Show "850 available", or "short by 50" in amber when the line's quantity is more than `available`. Call it when the warehouse or the lines change.

- **The order detail** gains `warehouse` (`{id, code, name}` or null) and, on each open line, `stock: { "available": "850", "short": false }`. `short` is true when the warehouse is over-committed. Null once the line has shipped, or for a user without stock access.

## Dispatch

`POST /orders/{id}/dispatches` takes an optional `warehouse_id`: where the goods left. It defaults to the order's warehouse, then the default. Each dispatch answers `warehouse: {id, code, name}`. Show a warehouse picker on the dispatch form, defaulting to the order's.

## The stock list: `GET /stock?warehouse_id=&product_id=&short_only=&limit=&cursor=`

```json
{ "data": [ { "warehouse": { "id": "uuid", "code": "AHD-1", "name": "Ahmedabad depot" },
              "product": { "id": "uuid", "code": "DL16-4LPH", "name": "Dripline 16 mm 4 LPH" },
              "on_hand": "1250", "committed": "400", "available": "850", "uom": "m" } ],
  "meta": { "next_cursor": "100" } }
```

`committed`: what submitted, approved and partly dispatched orders still owe. A negative `available` (or `on_hand`, after a dispatch) shows in red.

## Recording stock: `POST /stock/movements`

```json
{ "warehouse_id": "uuid", "kind": "receipt", "reference": "GRN 2231", "note": "From the Vadodara plant",
  "lines": [ { "product_id": "uuid", "qty": "250" } ] }
```

- `kind`: `receipt` (positive; an opening balance is a receipt referenced "Opening") or `adjustment` (may be negative).
- Answer `201`: `{ "data": { "movements": [ { "id", "product_id", "qty", "on_hand_after" } ] } }`.
- `409 negative_stock` (an adjustment below zero), `409 warehouse_inactive`, `409 product_inactive`, `422 qty_precision`.

## The ledger: `GET /stock/movements?warehouse_id=&product_id=&limit=&cursor=`

Newest first: `kind` (`receipt`, `adjustment`, `dispatch`, `dispatch_void`), `qty`, `reference`, `note`, `dispatch_no`, `order`, `created_by`, `created_at`.

## Warehouses (admin)

- `POST /warehouses` `{ "code", "name", "territory_id", "is_default", "is_active" }`; `PATCH /warehouses/{id}` with any of them.
- `is_default: true` moves the default. `409 default_warehouse`: make another the default before deactivating this one. `409 code_taken`: codes are unique, ignoring case.

## Screens

| Screen | Notes |
|---|---|
| Order form | "Order to" picker; per-line availability, amber when short |
| Dispatch form | warehouse picker, defaulting to the order's |
| Stock list | filters: warehouse, product, short only; negatives in red |
| Record stock (Dispatch) | warehouse, kind, reference, note, lines |
| Stock ledger | movements with their dispatch and order |
| Warehouses (admin) | add, edit, deactivate, set default |

## Defaults the client has not confirmed

- A shortfall warns and never blocks an order.
- Dealers keep no stock in the system.
- One default warehouse serves any order without a choice.
