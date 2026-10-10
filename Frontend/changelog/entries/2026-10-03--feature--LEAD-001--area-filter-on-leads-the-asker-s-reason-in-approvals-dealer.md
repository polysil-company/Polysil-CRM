---
date: 2026-10-03
type: feature
title: Area filter on leads, the asker's reason in approvals, dealer search by
  contact person
dataIds:
  - LEAD-001
  - APPR-001
  - LEAD-008
author: Nakul Srivastava
breaking: false
---

## Before

The backend shipped three things in #49 and #50 that the screens didn't use yet:

- **Leads by area (FS-020).** `GET /leads?territory_id=` takes up to 20 territories, and `GET /leads/areas` lists the states, districts or talukas that hold leads, with counts. The lead list could filter by stage, source and type, but not by where the lead is.
- **The asker's reason.** A salesperson writes a remark when asking for discount approval. The approvals queue now returns it as `request_remark`, but a manager deciding the request never saw it, so they had to open the quotation or phone the salesperson.
- **Dealer search by contact person.** `GET /lookups/partners?q=` now also matches the person to ask for at a dealer. The assign dialog's hint still said "name or code".

## Now

- **Area pill on the lead list.** It sits next to Stage, Source and Type.
  - It lists the districts that hold a lead you can see, each with how many. With one state (Gujarat today), it starts at that state's districts.
  - Tick several areas, or open a district (the arrow, named "Show talukas in Rajkot") to tick its talukas. "All districts" goes back.
  - A district includes every taluka and village under it. Its count matches the filtered list: Rajkot reads 33, and the list shows "1–25 of 33".
  - The backend takes at most 20 areas. Past that, the other boxes are disabled, with a note suggesting a district instead of its talukas.
  - The choice is kept in the URL (`?area=…`), so a refresh or a shared link keeps it. The pill names the area picked, or shows "3 areas". Clear area and Reset filters remove it.
  - States:
    - loading: three skeleton rows;
    - none: "No leads in any area yet";
    - a district whose leads aren't filed under a taluka: says to go back and choose the district itself;
    - error: the message and Try again.
  - The picker loads only when it is opened. It reopens where it was left, on a phone and a desktop, in light and dark.
- **The reason on approval requests.** The remark shows as a quote under each request in the inbox. It shows again at the top of the approve or reject dialog, as "Aarav Desai's reason: …". Requests raised without a remark look as before.
- **Dealer search.** The assign dialog's partner search says "Dealer name, code or contact person". The mock backend matches the contact person too, as the real one does.

## Discussion

- **Districts first, not one long list.** Gujarat has 33 districts and hundreds of talukas, so a flat list would be unusable on a phone. Drilling down keeps each list short, and the lead counts show where the work is.
- **Skipping the single state.** Choosing the only state would filter nothing, so with one state the picker starts one level down. A second state brings the state level back by itself.
- **The pill's name for an area.** The pill knows an area's name only after it is picked in this visit. A link opened fresh shows "1 area" until then. Resolving names would need another endpoint (`GET /territories/{id}`), which isn't worth a call per pill.
- **The 20-area limit is the backend's.** It is enforced in the UI, and the URL parser also caps it at 20, so a hand-edited link can't trigger a 422.
- **Shared code.** `FilterPillFrame` and `filterOptionRowClasses` are now exported from the filter-pill pattern, so the area pill looks and behaves exactly like the others. No visual change to the existing pills.

## Files changed

- `src/features/leads/api/leads.schemas.ts`:
  - `LeadListParams.areas`;
  - `LEAD_AREA_LEVELS`, `MAX_LEAD_AREAS`;
  - the `GET /leads/areas` schema and `LeadArea`.
- `src/features/leads/api/leads.api.ts`: `territory_id` on the list; `listLeadAreas`.
- `src/features/leads/api/leads.queries.ts`: `leadKeys.areas` and `leadAreasQueryOptions`.
- `src/features/leads/hooks/use-lead-list-params.ts`: `?area=` in the URL, validated, deduplicated and capped at 20; it counts as a filter and is cleared by Reset.
- `src/features/leads/components/lead-area-filter.tsx`: new, the Area pill and its drill-down picker.
- `src/features/leads/components/leads-toolbar.tsx`: the Area pill; the skeleton gains a fourth pill.
- `src/features/leads/components/lead-assign-dialog.tsx`: the partner search hint.
- `src/components/patterns/filter-pill.tsx`: exports `FilterPillFrame` and `filterOptionRowClasses`.
- `src/features/approvals/api/approvals.schemas.ts`: `request_remark` becomes `requestRemark`.
- `src/features/approvals/components/approvals-inbox.tsx`: the reason under each request.
- `src/features/approvals/components/approval-decision-dialog.tsx`: the reason in the dialog.
- `src/mocks/handlers/leads.ts`: `GET /leads/areas`; `territory_id` filtering by a lead's territory or any area above it.
- `src/mocks/data/territories.ts`: `mockTerritoryLineage`.
- `src/mocks/handlers/lookups.ts`, `src/mocks/data/reference.ts`: partners carry a contact person, and search matches it.
- `src/mocks/data/approvals.ts`, `src/mocks/handlers/approvals.ts`, `src/mocks/handlers/quotations.ts`: approval steps keep the request remark and return it.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Plan.md` §9, `Docs/Tested-Features.md`: the records.
- `Docs/screenshots/area-filter/`, `Docs/screenshots/approvals/`: the new screens.

## Tests

- **`src/features/leads/api/leads.test.ts`:**
  - `[LEAD-001] listLeads`:
    - filtering by a district matches its count;
    - several areas go as one comma-separated `territory_id`, and none when unset.
  - `[LEAD-001] listLeadAreas`:
    - the levels and counts;
    - the level and parent sent;
    - a contract violation.
  - `[LEAD-008]`: finds a partner by contact person.
- **`src/features/leads/components/leads-ui.test.tsx`:**
  - drill from districts to Rajkot's talukas and back;
  - the URL and the request carry the area;
  - the pill names it;
  - Clear removes it;
  - a district with no taluka-level leads explains itself;
  - a load error offers Try again.
- **`src/features/approvals/components/approvals-inbox.test.tsx`:** the reason shows on the row and in the dialog, and only where one was given.
- **By hand, in Chromium on the mock backend:**
  - Leads, Area: Rajkot narrows 132 to 33, and the URL keeps it;
  - talukas in Rajkot;
  - a phone in dark mode;
  - Approvals: the reason on four rows and in the approve dialog;
  - axe found nothing on the open picker or the dialog.
