# Subsidy schemes: setting up a new state

> An admin adds another state's subsidy scheme, sees what it still lacks, and applications pick the scheme from the lead's state. Full spec: FS-039. Built: the generated API doc `subsidy-schemes.md` is the record.

## What changes for existing screens

- **Subsidy calculation preview and the application form:** stop sending `scheme: "GGRC"` by default. Ask `GET /subsidy-schemes/for-lead/{lead_id}` and send its `code`. A UP lead with `GGRC` in the request is refused with 422.
- **Application stage picker:** pass the application's `scheme` to `GET /subsidy-stages?scheme=`.
- **Commission rates screen:** pass the scheme to `GET /commission-rates?scheme=`.
- **Subsidy masters screens (handover 45):** add a scheme selector. Every endpoint there already takes `scheme`.

## Endpoints

```jsonc
// GET /api/v1/subsidy-schemes                        signed in
{ "data": [ { "code": "GGRC", "name": "Gujarat Green Revolution Company", "is_active": true,
              "state": { "id": "uuid", "code": "GJ", "name": "Gujarat" },   // null: not tied to a state
              "systems": ["drip", "mini_sprinkler", "sprinkler"],
              "ready": true, "applications": 41 } ] }

// GET /api/v1/subsidy-schemes/{code}?on=2026-10-08    the readiness panel
{ "data": { "code": "UPMIS", "name": "UP Micro Irrigation", "is_active": true,
  "state": { ... }, "on": "2026-10-08",
  "systems": [ { "system_type": "drip", "ready": false,
                 "missing": ["unit_cost_matrix:regular", "categories", "parameters:insurance_rate"] } ],
  "stages": [ { "seq": 4, "code": "application_in_process", "name": "Application in process", "is_active": true } ],
  "ready": false } }

// POST /api/v1/subsidy-schemes                       masters.edit, Idempotency-Key
{ "code": "UPMIS", "name": "UP Micro Irrigation", "state_territory_id": "uuid",
  "template": "GGRC", "systems": ["drip", "sprinkler"] }   // template and systems optional
// 201: the detail body
// 409 code_taken | state_has_scheme | unlinked_scheme_exists   422 fields

// PATCH /api/v1/subsidy-schemes/{code}               masters.edit
{ "name": "...", "is_active": false, "state_territory_id": "uuid" }   // any of them
// state_territory_id only while the scheme has none (how GGRC gets linked to Gujarat)
// 409 state_has_scheme | unlinked_scheme_exists | state_fixed

// PATCH /api/v1/subsidy-schemes/{code}/stages/{stage_code}   masters.edit
{ "name": "UP query" }

// GET /api/v1/subsidy-schemes/for-lead/{lead_id}
{ "data": { "code": "GGRC", "name": "...", "ready": true } }
// 422 no_scheme_for_state | territory_without_state_code
```

## Reading `missing`

Each item is something a calculation on that system would refuse on, in the order it would refuse. Link each to the masters screen that fills it:

| Item | Masters screen |
|---|---|
| `unit_cost_matrix:regular`, `unit_cost_matrix:seven_year` | unit cost matrices |
| `quantity_matrix`, `quantity_matrix:<row>` (a row missing or short of an area) | quantity matrices |
| `categories` | categories |
| `crop_spacings` | crop spacings |
| `parameters:<key>` | parameters, that key |
| `component_rate:<code>:<75, 90, plastic or brass>`, `component_rate:transport` | component rates |
| `stages` (top level) | none: the scheme has no active stage. Tell the user to contact support |

## Screens

1. **Subsidy schemes** (admin settings): list with a ready badge and a "New scheme" button. If any scheme shows `state: null`, show a banner: "Link GGRC to its state before adding another state's scheme." The PATCH with `state_territory_id` does that.
2. **New scheme:** code, name, state (states without an active scheme), template (default GGRC), systems checklist.
3. **Scheme detail:** the readiness panel, stage rename, and a switch-off toggle. Put the application count in the confirm text.
4. **Calculation and application forms:** "Subsidy for this state is not set up yet" when `for-lead` returns `ready: false` or 422.

## Not built

- A new calculation formula for a state (GAP-359).
- Adding or reordering stages (GAP-361).
- The PIMS export for other states: 422 `pims_not_for_scheme` (GAP-363).
