import type { Lead } from "@/features/leads/api/leads.schemas";

import { generateLeads } from "./data/leads";

/** In-memory state of the mock backend. Created leads live until the page reloads. */
export const mockDb: { leads: Lead[] } = {
  leads: generateLeads(),
};

export function resetMockDb(): void {
  mockDb.leads = generateLeads();
}
