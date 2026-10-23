# Subsidy calculation: what the frontend needs

The calculation engine is built and the endpoints are live. This is what you need
to build the quotation screen against it. The generated contract is
`backend/docs/api/subsidy.md`, which is the record; this document is the context
around it.

---

## The shape of the thing

A quotation covers **one irrigation system** and **one or more crops**. The
farmer's land is divided into crop blocks, each with its own area, its own
spacings and its own list of parts. The head unit, the pump-end equipment, is
shared by the whole quotation and is sent once.

You send that, you get back a cost breakdown per crop, a total column, and a
table of farmer categories. Each category row says what the government scheme
pays and what the farmer pays.

**Nothing is stored.** `POST /subsidy/calculate` is a preview. Call it as the
designer types, debounced. It takes no `Idempotency-Key` and changes nothing, so
a retry is free.

---

## The three systems are three different screens

Do not build one form with toggles. The systems genuinely differ:

| | Drip | Mini Sprinkler | Sprinkler |
|---|---|---|---|
| Crop blocks | up to 2 | 1 | 1 |
| Head unit | yes | yes | none |
| Lines | typed by the designer | typed by the designer | **derived, send none** |
| Group sharing | yes | yes | no |
| Extra input | none | none | nozzle: plastic or brass |
| Area | any | any | **only tabulated steps** |

`GET /subsidy/config` returns all of this per system, including the list of areas
a Sprinkler quotation may use. Read it once when the screen loads and drive the
form from it, rather than hard-coding the table above. It also returns the rates
behind the sums, so a screen that prints "insurance at 0.28 %" stays correct when
the scheme changes the figure.

---

## Fields that need explaining to the user

**The unit cost the scheme allows.** Each crop returns three: `regular` is the
interpolated figure, `regular_with_sump` adds the sump, and **`regular_for_cap`
is the one the subsidy is actually capped on**. They are equal except for a Mini
Sprinkler block below 0.2 hectares, where the scheme pro-rates. Print
`regular_for_cap`: it is the figure on the client's own sheet, and it is the only
one that explains the subsidy beside it.

**Lateral spacing.** The designer enters the spacing they planned. The scheme has
its own standard spacing per crop, and **the calculation runs at the larger of the
two**. So a designer who plans tighter than the standard sees no extra subsidy.
Show both: the response returns `lateral_spacing_designed`,
`lateral_spacing_standard` and `lateral_spacing_for_subsidy` per crop, and a user
who does not see why their number was ignored will ask.

**Inter-crop.** If a block carries a second crop, **the inter-crop sets the
standard spacing, not the main crop**. This is easy to miss and it is worth real
money: on the client's own sample quotation it is a difference of ₹78,780 of
subsidy. Put both pickers next to each other, from `GET /subsidy/crops`, which
returns each crop with its standard spacing so you can show it inline.

**Group total area.** When several farmers share one water source, the head unit
is split across all of them by area. `group_total_area` is everyone's land, and it
must be at least the sum of the crops on this quotation. Leave it out for a
farmer quoting alone.

**Sump.** Optional, a rate per hectare. It is the farmer's own cost: it raises the
allowed unit cost but is subtracted from the farmer's share.

---

## Money on the wire

Every money value is a **decimal string** with two decimals: `"199818.16"`. Areas
carry three, unit costs four. Never parse them into a JavaScript number and back;
a float cannot hold a rupee figure exactly and the quotation has to match the
client's own spreadsheet to the paisa.

**A column may not visibly add up.** Block values are rounded for display, and the
engine only rounds where the scheme's workbook rounds. On the Drip sample, the
head unit `7235.79` plus the field unit `187601.19` shows as `194836.98`, while
`a_plus_b` is `194836.99`, because that cell is rounded and the two above it are
not. This is correct and matches the client's tool. Do not compute subtotals on
the client to "check" the server.

---

## Warnings are part of the response

`warnings` appears on the response and on each crop. Each is one string shaped
`code: sentence` - split on the first colon, switch on the code, show the
sentence. **Show them.** They mark the cases where the engine deliberately does
something other than what the client's spreadsheet does, and a designer who hits
one needs to know:

| Code | What it means for the user |
|---|---|
| `spacing_outside_table` | the spacing is outside the range the scheme tabulates; the figure uses the nearest tabulated row |
| `area_below_table` | the area is below the smallest tabulated one |
| `area_above_table` | the area is above five hectares; the unit cost is scaled |
| `seven_year_not_applicable` | the seven-year rows do not apply at this total area |
| `rounding_residual` | the total column differs from the sum of the crops by a paisa of rounding |
| `sump_ignored_by_workbook` | the sump is being counted here, where the client's spreadsheet does not count it |

The first three also appear prefixed - `seven_year_spacing_outside_table`,
`seven_year_area_below_table`, `seven_year_area_above_table` - when it is the
seven-year table that was clamped rather than the regular one. Both can arrive
together on the same crop, and they mean different figures, so handle the prefix
rather than matching the bare code.

---

## The category table

Eight rows, always all eight, in the order the quotation prints them. A row that
does not apply comes back with `applicable: false`, a `reason`, and `"0.00"` in
every money field. **Render it, greyed, rather than dropping it** - a farmer
looking for their own category and not finding the row will assume the quote is
broken.

`gsdma_farmer_share` is filled only for Mini Sprinkler at two hectares or less,
and is `null` everywhere else. It is a second scheme running alongside the main
one.

---

## Errors

A `422` carries `fields`, a map from field path to reason, with paths like
`crops[0].area` so you can mark the offending input directly. The paths match the
request shape exactly.

Two refusals will surprise users, so word them carefully in the UI:

- **A Sprinkler area that is not a tabulated step.** The scheme's table has
  0.4 to 5.0 in steps of 0.2, plus 2.01. The message names them. This is the
  scheme's limitation, not ours, and there is an open question with the client
  about whether it should round instead.
- **An unknown scheme code** comes back as a `422` naming the `scheme` field. A
  `404` means something different: the scheme and system are fine, but no master
  table is in force on the date you asked for.
- **A crop name that is not in the crop table.** Send exactly what
  `GET /subsidy/crops` returned. Matching ignores case and surrounding spaces, but
  an unknown name is refused rather than silently treated as no crop, because a
  silent miss would quietly change the subsidy.

---

## Permissions

Every endpoint needs `subsidy.view`. Every field and management role holds it;
**dealer and distributor portal users do not** and get a `403`. Do not put the
quotation screen behind the dealer portal navigation.

---

## Endpoints

| | |
|---|---|
| `POST /api/v1/subsidy/calculate` | the calculation; no idempotency key |
| `GET /api/v1/subsidy/config` | what each system accepts, and the rates |
| `GET /api/v1/subsidy/crops` | the crop picker, with standard spacings |
| `GET /api/v1/subsidy/categories?system_type=` | the category labels, before anything is calculated |

Full request and response shapes, field by field, are in
`backend/docs/api/subsidy.md`.

---

## What is not built yet

The calculation only. Applications, the seventeen tracked stages, documents and
the PIMS export are the next piece of work and will add their own endpoints.
Nothing here writes to the database, so there is no application id to hold on to
yet.
