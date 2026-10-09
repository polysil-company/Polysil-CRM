import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";

import { MOCK_STATE } from "./reference";
import { MOCK_STAGE_DEFS } from "./subsidy-applications";
import { MOCK_TERRITORIES } from "./territories";

/**
 * SUBS-014 · The mock's subsidy schemes. GGRC is linked to Gujarat, as migration 044's backfill
 * does wherever a GJ state exists; Uttar Pradesh has none yet, so a second scheme can be set up.
 */

export interface MockSchemeStage {
  readonly seq: number;
  readonly code: string;
  name: string;
  readonly is_active: boolean;
}

export interface MockScheme {
  readonly code: string;
  name: string;
  is_active: boolean;
  /** Null: not tied to a state yet (the legacy GGRC before it is linked). */
  state_territory_id: string | null;
  readonly systems: readonly SystemType[];
  readonly stages: MockSchemeStage[];
}

/** The scheme every mock lead's state ran before 044. */
export const MOCK_DEFAULT_SCHEME = "GGRC";

export function mockStateTerritoryId(code: string): string | null {
  return (
    MOCK_TERRITORIES.find((territory) => territory.level === "state" && territory.code === code)
      ?.id ?? null
  );
}

export function seedSubsidySchemes(): MockScheme[] {
  return [
    {
      code: MOCK_DEFAULT_SCHEME,
      name: "Gujarat Green Revolution Company",
      is_active: true,
      state_territory_id: mockStateTerritoryId(MOCK_STATE.code),
      systems: SYSTEM_TYPES,
      stages: MOCK_STAGE_DEFS.map((stage) => ({
        seq: stage.seq,
        code: stage.code,
        name: stage.name,
        is_active: true,
      })),
    },
  ];
}
