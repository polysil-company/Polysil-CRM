# The dev API: where it is and how to use it

A running backend for you to build against, on a development box until the
client's server arrives. Real data, real rules, real errors.

---

## The URL

```
https://polysil-api.pranayx.tech
```

| | |
|---|---|
| Interactive docs | https://polysil-api.pranayx.tech/docs |
| OpenAPI schema | https://polysil-api.pranayx.tech/openapi.json |
| Health | https://polysil-api.pranayx.tech/health |
| Everything else | `https://polysil-api.pranayx.tech/api/v1/...` |

**Generate your client from the schema rather than hand-writing types.** That URL
is the contract, and it changes when we ship. `backend/docs/api/*.md` in the repo
is the same thing as readable prose, one file per module.

---

## Signing in

Three staff users and one dealer. Ask us for the password; it is not written
down here, and it is not in the repository either.

| Who | How | What they see |
|---|---|---|
| `admin@polysil.in` | email and password | everything, globally |
| `asha@polysil.in` | email and password | a district manager: her district only |
| `ravi@polysil.in` | email and password | a field officer: **his own records only** |
| `919876543210` | mobile and a one-time code | a dealer, through the partner portal |

**Use all four while you build.** The three staff users see genuinely different
data, because the rules are enforced in the database rather than in the screens.
A list that looks empty for Ravi and full for the admin is working correctly.

```http
POST /api/v1/auth/login
{ "email": "asha@polysil.in", "password": "..." }

-> 200  { "data": { "access_token": "...", "expires_in": 900 } }
        Set-Cookie: polysil_refresh=...   (httpOnly, you never read it)
```

Send the access token on everything else as `Authorization: Bearer <token>`.
It lasts fifteen minutes; call `POST /api/v1/auth/refresh` to get a new one. The
refresh token is in an httpOnly cookie, so **send `credentials: "include"` on
that call** or the browser will not attach it.

The dealer's one-time code is not sent anywhere yet, because the client's
WhatsApp account is not connected. Ask us for the code and we will read it out of
the database.

---

## CORS, which is already set up

Any port on your own machine is allowed: `http://localhost:*` and
`http://127.0.0.1:*`. You do not need to tell us which port your dev server picked.

```ts
fetch("https://polysil-api.pranayx.tech/api/v1/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",          // needed, or the refresh cookie is not stored
  body: JSON.stringify({ email, password }),
})
```

**When you deploy a preview** (Vercel, Netlify, anywhere with its own domain),
send us the URL. A deployed origin has to be named explicitly; a pattern cannot
cover it, because the browser refuses a wildcard on any request carrying
credentials.

---

## What the API gives you back

**Success is always `{ "data": ... }`.** Never a bare array or a bare value, so a
field can be added later without breaking your parse.

**Failure is always `{ "error": { "code", "message" } }`.** Switch on `code`;
`message` is written for a person and may be reworded. A `422` also carries
`fields`, a map from the field's path to what is wrong with it, using the same
path as your request:

```json
{ "error": { "code": "validation_error", "message": "Some fields need correcting.",
             "fields": { "crops[0].area": "Sprinkler areas are tabulated in 0.2 Ha steps..." } } }
```

**Money and quantities are decimal strings**, never numbers: `"199818.16"`. Do not
parse them into a JavaScript number and back. A float cannot hold a rupee figure
exactly, and these quotations have to match the client's own spreadsheets to the
paisa.

**Every mutation takes an `Idempotency-Key` header**, a UUID you generate. Replay
the same key with the same body and you get the first response back rather than a
second record. That is what makes a retry on a flaky connection safe.

---

## What is there to build against

| Area | State |
|---|---|
| Sign-in, sessions, refresh, sign-out | done |
| People, roles, offices, territories, channel partners | done |
| Leads: capture, lifecycle, assignment, duplicates, timeline, lookups | done |
| Subsidy calculation: three systems, eight farmer categories | done |
| Products, prices, tax | done — catalogue, price lists, and a pricing preview |
| Quotations, orders, dispatch | not started |

Three handover notes worth reading before you build those screens:
`14-Administration-and-Sign-in-Handover.md`,
`15-Subsidy-Calculation-Handover.md` and
`17-Products-and-Pricing-Handover.md`. They cover the things the generated API
docs cannot, like why a column of figures may not visibly add up, and why CGST
and SGST are always equal.

---

## Things that will look like bugs and are not

**A field officer sees fewer rows than an admin.** That is the access model doing
its job, enforced in the database. Do not work around it in the UI.

**A product says `provisional_fields`.** The client has not sent real prices or
tax codes yet, so those figures are realistic stand-ins of ours. **Show that
badge.** A quotation built on them is fine for testing and must not go to a
farmer.

**A subsidy response carries `warnings`.** Each is one string shaped
`code: sentence`. Split on the first colon, switch on the code, show the
sentence. They mark places where the engine deliberately differs from the
client's own spreadsheet, and the person on the screen is the only one who can
judge it.

**An empty list is an empty list**, not an error. It means nothing is in that
user's scope.

---

## The data on this box

Real: the client's 1,092 products with their categories and units, the subsidy
unit-cost tables, the 79 crops and their spacings.

Invented: all prices and tax codes, marked as above. A handful of demo users,
offices and territories.

**It is a development box, so treat the data as disposable.** It is separate from
the database we develop against, so you cannot break our work, and we can reset
yours if it gets messy. Tell us before you do anything that would take a while to
redo.

---

## If it stops answering

Check https://polysil-api.pranayx.tech/health first. If that is silent, tell us,
it is ours to fix. The box also hosts other things, so please do not restart
anything on it.

Two limits that are meant to be there, and will look like the API is broken if
you hit them in a loop: **five failed sign-ins in fifteen minutes locks that
email address** for fifteen, and a mobile number may request **three codes per
fifteen minutes and ten a day**.
