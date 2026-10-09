# Consumer portal

> Full spec: FS-044. All additive. **Off by default.**

A farmer signs in with their mobile and a WhatsApp code and sees their own record. Question 10.3 (what farmers should do there) is unanswered, so this round is read-only plus consent. Question 10.4 suggests a separate, simple app from the dealer portal.

## Switching it on (admin)

`PATCH /api/v1/settings` with `{"values": {"consumer_portal": "on"}}`. Off ends every farmer's session. Switching on means every customer number can be sent a paid WhatsApp code.

## Sign in

The existing `POST /api/v1/auth/otp/request {mobile}` and `POST /api/v1/auth/otp/verify {mobile, code}`. A farmer has an account once one of their enquiries is qualified.

## The farmer's screens

| Call | Answer |
|---|---|
| `GET /portal/me` | `name`, `mobile`, `email`, `village`, `territory_name`, `consent_given_at`, `consent_channel` |
| `PATCH /portal/me {consent_given}` | `Idempotency-Key`. `true` records consent (channel `portal`); sending it again keeps the first date. `false` withdraws it |
| `GET /portal/enquiries` | `inquiry_no`, `status` (`in_progress`, `won`, `closed`), `system`, `created_at` |
| `GET /portal/quotations` | `quote_no`, `status` (`sent`, `accepted`, `closed`), `total`, `sent_at`, `valid_until`, `link` |
| `GET /portal/orders` | `order_no`, `status` (`in_progress`, `being_revised`, `dispatched`, `closed`, `cancelled`), `total`, `submitted_at`, `dispatches: [{dc_no, dispatched_at}]` |
| `GET /portal/complaints` | `complaint_no`, `status` (`in_progress`, `closed`), `raised_at` |

- Lists are newest first, at most 100.
- A document bought through a dealer shows no `total` and no `link`.
- An enquiry appears once qualified.

## Errors

| Code | When |
|---|---|
| `401` | not signed in, or the portal was switched off: sign in again |
| `403 not_a_consumer` | a staff or dealer token on `/portal` |
| `403 portal_off` | the portal is off |
| `403 consumer_not_allowed` | a farmer's token on any route outside `/auth` and `/portal` |

## Screens

1. Sign in: mobile, then the code.
2. Home: enquiries, quotations (open `link`), orders with dispatches, complaints.
3. A consent switch.
4. Admin: a "Consumer portal" switch in settings, with the cost warning.

The people list (`GET /users`) leaves farmers out unless `user_type=consumer` is asked.
