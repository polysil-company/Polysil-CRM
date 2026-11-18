# Dealer credit limit at submit

> Full spec: FS-027. All additive. One new endpoint.

## The setting (admin)

One more row in the settings list (`GET /api/v1/settings`, `PATCH /api/v1/settings`):

```jsonc
{ "key": "dealer_credit_check", "kind": "choice", "value": "warn",
  "allowed": ["off", "warn", "block"],
  "description": "On submitting a dealer's order: ignore its credit limit, warn the approvers, or refuse the order." }
```

Suggested label: "Dealer credit limit at submit". Options: "Off", "Warn the approvers", "Refuse the order".

## Submitting an order

`POST /api/v1/orders/{id}/submit` is unchanged. What happens depends on the setting, and only for an order with a dealer whose credit limit is set:

| Setting | Over the limit |
|---|---|
| `off` | nothing |
| `warn` | 200 as today; the order has `over_credit_limit: true` |
| `block` | **409** `credit_limit_exceeded`, message "This order would take the dealer over its credit limit." The order stays a draft |

The 409 carries no amounts. Show the message, and suggest asking Accounts.

A refused submit is stored against its `Idempotency-Key`. After the limit is raised, submit again with a **new** key.

## On the order

`GET /orders/{id}`, the order list and the approval queue gain `over_credit_limit`:

| Value | Show |
|---|---|
| `true` | an "Over credit limit" badge |
| `false` or `null` | nothing |

Only approvers, dealer editors and Accounts get a value. Field officers and dealers always get `null`.

## A dealer's credit (Accounts and admin)

```jsonc
// GET /api/v1/partners/{id}/credit
{ "data": { "partner_id": "...",
            "credit_limit": "500000.00",   // null: no limit set
            "exposure": "432100.00",        // owed on open orders less receipts; negative means in credit
            "available": "67900.00",        // null when there is no limit
            "check": "warn" } }
// 403 for field officers, dealers and distributors, and for a manager outside the dealer's area
```

Suggested place: the dealer detail page, beside the ledger, with "Limit", "Owed" and "Available".
