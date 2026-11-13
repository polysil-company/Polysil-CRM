---
date: 2026-10-15
type: feature
title: "Dormant leads: the banner, reopen and lost"
dataIds:
  - LEAD-007
author: Nakul Srivastava
breaking: false
---

## Before

The backend moves a lead with no activity for a while to `dormant` overnight (FS-035, `lead-small-gaps-contract.md`). It sends `dormant_from_stage`, the stage Reopen returns it to. It lets a dormant lead be reopened (`POST /leads/{id}/reopen`) or closed as lost (`POST /leads/{id}/transition`).

The frontend showed a "Dormant" badge with no menu and no explanation. Nobody could bring the lead back or close it.

## Now

- **A dormant lead's page** says "Dormant: no activity for a long time".
  - It shows where the lead was ("It was Qualified").
  - It explains that the lead can still be edited, assigned and given tasks, while a quotation waits until it is reopened.
- **Update stage** offers:
  - **Reopen lead…**, back to the stage it stood at. The dialog names that stage. The reopen count stays as it was, as the backend keeps it for conversion reports.
  - **Mark as lost…**, with the usual reason.
- **The reopen description** now reads "Back to the stage it was at before", which holds for both a lost lead and a dormant one.
- **The stage help** for Dormant says it can be reopened or marked lost.
- **The mock** follows the backend:
  - seeded dormant leads came from Qualified;
  - reopening returns there;
  - a dormant lead can move to lost, and if reopened later it goes back to where it went dormant.
- Checked on a desktop in light mode and a phone in dark mode: the lead, the menu, the reopen dialog and the reopened lead. axe found nothing.

## Discussion

- **The banner says "a long time", not "60 days".** The period is the `dormant_after_days` setting, which the lead page doesn't read. The backend records the move to Dormant in the lead's history.
- **No buttons in the banner:** reopen and lost stay in Update stage, beside the other stage moves. The banner points there.
- **Conflict to expect with #132:** #132 (dealership enquiries) changes `stageMenuFor` and `stageActionDescription` too. Whichever merges second keeps both changes: the dormant case here, and the dealership arguments there.
- **The backend's API doc** still says only a lost lead can be reopened. Its code (`services/leads.py`, `REOPENABLE`) reopens dormant ones too, and this follows the code.
- **Not yet checked on staging.**

## Files changed

- `src/features/leads/api/leads.schemas.ts`: `dormant_from_stage` → `dormantFromStage`.
- `src/features/leads/lib/lead-lifecycle.ts`: a dormant lead's menu, and the reopen description.
- `src/features/leads/lib/lead-labels.ts`: the Dormant stage help.
- `src/features/leads/components/lead-detail.tsx`: the dormant banner.
- `src/features/leads/components/lead-stage-dialog.tsx`: the reopen dialog for a dormant lead.
- `src/mocks/handlers/leads.ts`, `src/mocks/data/leads.ts`: dormant reopen and lost, and `dormant_from_stage` on the seed.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/leads/dormant-*`: records and screens.

## Tests

- `src/features/leads/lib/lead-lifecycle.test.ts`: a dormant lead offers reopen or lost.
- `src/features/leads/components/lead-dormant.test.tsx`:
  - `dormant_from_stage` read;
  - reopened to Qualified without counting a reopen;
  - lost from dormant, then reopened, back to where it went dormant;
  - the banner and the menu;
  - reopening from the page.
- Walked through in the mock: desktop light and phone dark.
