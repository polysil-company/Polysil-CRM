import type { LookupList, LookupListWire } from "@/features/lookups/api/lookups.schemas";

import { MOCK_ID_SPACE, mockUuid } from "./reference";

type LookupRow = LookupListWire["data"][number];

/** The backend's seeded rows (backend/api/db/migrations/versions/006_leads.py), in its order. */
const SEEDS: Readonly<Record<LookupList, readonly (readonly [code: string, name: string])[]>> = {
  "lead-sources": [
    ["whatsapp", "WhatsApp"],
    ["website", "Website"],
    ["employee", "Employee"],
    ["dealer", "Dealer"],
    ["campaign", "Campaign"],
    ["agri_fair", "Agri Fair"],
    ["farmer_meeting", "Farmer Meeting"],
    ["qr_code", "QR Code"],
    ["form_link", "Form Link"],
  ],
  "mis-systems": [
    ["drip", "Drip"],
    ["mini_sprinkler", "Mini Sprinkler"],
    ["sprinkler", "Sprinkler"],
    ["automation", "Automation"],
    ["other", "Other"],
  ],
  "lost-reasons": [
    ["price", "Price"],
    ["competitor", "Competitor"],
    ["no_response", "No response"],
    ["product_mismatch", "Product mismatch"],
    ["financing_not_approved", "Financing not approved"],
    ["out_of_area", "Out of area"],
  ],
};

const LIST_OFFSET: Readonly<Record<LookupList, number>> = {
  "lead-sources": 100,
  "mis-systems": 200,
  "lost-reasons": 300,
};

/** Every row of one list, as GET /lookups/{list} returns it. */
export function mockLookupRows(list: LookupList): LookupRow[] {
  return SEEDS[list].map(([code, name], index) => ({
    id: mockUuid(MOCK_ID_SPACE.lookup, LIST_OFFSET[list] + index + 1),
    code,
    name,
    is_active: true,
  }));
}

/** The codes of one list, for generating leads that use them. */
export function mockLookupCodes(list: LookupList): string[] {
  return SEEDS[list].map(([code]) => code);
}
