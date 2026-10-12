# Farmers rate from the portal: what to build

A farmer rates his own installation and service visits from the consumer portal. The full contract is `backend/docs/api/portal.md`; this page is the screen view.

## Calls

| Call | Use |
|---|---|
| `GET /api/v1/portal/ratings` | His ratings, newest first: the ones he gave and the ones an officer recorded for him. Each row has `target` (`installation` or `service`), `order_no` or `complaint_no`, `score`, `comment`, `entered_via` (`portal` or `staff`), `created_at` |
| `POST /api/v1/portal/ratings` | Rate one. Body: `target`, `order_no` (installation) or `complaint_no` (service), `score` 1 to 5, `comment` optional, up to 1000 characters. `Idempotency-Key` required. Answers `201` with the new row |

## Screens

**My orders.** On an order with at least one dispatch and no installation rating in `GET /portal/ratings` for that `order_no`, show **Rate the installation**. It opens 1 to 5 stars and an optional comment. Once rated, show the stars and "Rated". There is no edit.

**My complaints.** The same for a complaint whose status is `closed`: **Rate the service**. The portal's `closed` also covers a complaint that was cancelled or rejected. Rating one of those answers `422 not_rateable`: remove the button and show "There was no service visit to rate."

**An officer's rating for him** comes back with `entered_via: "staff"` and `comment: null`. Show the stars with "Recorded by our team". He cannot add his own.

## Errors

| Status | Code | Show |
|---|---|---|
| 404 | `not_found` | "We could not find that order." (another farmer's number, or a typo) |
| 409 | `rating_exists` | "This has been rated already." Refresh the list |
| 422 | `not_rateable` | "You can rate this once it has been delivered" (order) or "once the complaint is closed" |
| 403 | `portal_off` | the portal's usual switched-off screen |

## Staff side, no new screen

- Staff ratings rows gain `entered_via`: `staff`, `portal` or `dealer`. For `portal`, `entered_by` is `null`: show "the farmer, from the portal".
- On order and complaint timelines, a `rating.recorded` event from the portal has `payload.via = "portal"` and `payload.actor_name` set to the farmer's name.
