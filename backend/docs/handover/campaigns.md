# Campaigns

> Full spec: FS-040. All additive.

## The campaign list

```jsonc
// GET /api/v1/campaigns?active=true&type=agri_fair&q=mela     any staff user; a dealer gets 403
{ "data": [ {
    "id": "uuid", "name": "Krishi Mela Rajkot 2026", "type": "agri_fair",
    "territory": { "id": "uuid", "name": "Rajkot", "level": "district" },   // or null
    "start_date": "2026-10-20", "end_date": "2026-10-22",                   // null end: one day
    "cost_planned": "150000.00", "cost_actual": null,   // null unless campaigns.view
    "description": null, "is_active": true,
    "lead_count": 12,                                    // leads you can see
    "created_at": "...", "updated_at": "..." } ] }
```

- Newest start first, at most 500, no paging.
- Types: `exhibition`, `agri_fair`, `farmer_meeting`, `dealer_meet`, `promo_drive`, `digital`, `print`, `other`.
- Cost shows for Marketing, Admin Sales, the MD and the board. Everyone else gets null.

## Writing (Marketing only)

| Call | Notes |
|---|---|
| `POST /campaigns` | `name`, `type`, `start_date` required; `territory_id`, `end_date`, `cost_planned`, `cost_actual`, `description` optional. `409 campaign_name_taken` (case ignored) |
| `PATCH /campaigns/{id}` | any field, plus `is_active`. Null clears `end_date`, `territory_id`, `cost_actual`, `description` |
| `DELETE /campaigns/{id}` | `204`, or `409 campaign_in_use` once anything names it. Offer "Switch off" instead |
| `GET /campaigns/{id}` | adds `summary`: `leads`, `won`, `lost`, `open`, `sales_value`, `cost_per_lead`, `cost_per_won` |

Every write takes `Idempotency-Key`.

## On a lead

- `POST /leads` and `PATCH /leads/{id}` take `campaign_id`. Use `GET /campaigns?active=true` for the picker. PATCH null clears it.
- The Lead has `campaign_id` and `campaign_name`. Both are null for a dealer.
- `GET /leads`, `/leads/stats`, `/leads/export` take `campaign_id=<uuid>` or `campaign_id=none`.
- The export has a Campaign column.

## On a QR code

- `POST` and `PATCH /lead-qr-codes` take `campaign_id`. A code shows `campaign_id` and `campaign_name` beside the free-text `campaign`.
- Leads from a linked code get the campaign. The public form shows its name.

## The report

`GET /api/v1/reports/campaign-performance?from=&to=&territory_id=&owner_id=&format=json|xlsx`

Each row has:
- the `campaign` (id, name, type, dates, active);
- lead counts: `leads`, `qualified`, `won`, `lost`, `open`, `conversion_pct`;
- sales: `sales_count` (orders), `sales_value`. Null without the orders permission;
- cost: `cost_planned`, `cost_actual`, `cost`, `cost_per_lead`, `cost_per_won`. Null without `campaigns.view`.

It also returns `totals` (`leads`, `won`, `sales_value`, `cost`).

- The window picks leads by creation date. Their sales count whenever they happen.
- A campaign whose dates overlap the window shows with zeros, so spend with no leads is visible.
- Cost per lead is right only when the window covers the whole campaign.

## Screens

1. Campaigns (Marketing): the list, the form, a "Switch off" toggle.
2. A campaign picker on the lead form and the QR code form; the name on lead detail; a filter on the lead list.
3. Reports: Campaign performance, with the Excel download.
