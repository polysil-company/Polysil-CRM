import type { TerritoryWire } from "@/features/lookups/api/lookups.schemas";

import {
  MOCK_DISTRICT_OFFICES,
  MOCK_DISTRICTS,
  MOCK_ID_SPACE,
  MOCK_OTHER_STATE,
  MOCK_STATE,
  MOCK_STATE_OFFICE,
  MOCK_TALUKAS,
  MOCK_UNCOVERED_DISTRICT,
  mockUuid,
} from "./reference";

/** A territory with the district it sits in, for routing a mock lead to an office. */
export interface MockTerritory extends TerritoryWire {
  readonly district: string | null;
}

function buildTerritories(): MockTerritory[] {
  let index = 0;
  const nextId = (): string => mockUuid(MOCK_ID_SPACE.territory, (index += 1));

  const state: MockTerritory = {
    id: nextId(),
    name: MOCK_STATE.name,
    level: "state",
    code: MOCK_STATE.code,
    parent: null,
    district: null,
  };
  const territories: MockTerritory[] = [state];

  for (const [districtName, code] of MOCK_DISTRICTS) {
    const district: MockTerritory = {
      id: nextId(),
      name: districtName,
      level: "district",
      code,
      parent: { id: state.id, name: state.name, level: state.level },
      district: districtName,
    };
    territories.push(district);

    for (const [talukaName, villages] of Object.entries(MOCK_TALUKAS[districtName] ?? {})) {
      const taluka: MockTerritory = {
        id: nextId(),
        name: talukaName,
        level: "taluka",
        code: null,
        parent: { id: district.id, name: district.name, level: district.level },
        district: districtName,
      };
      territories.push(taluka);

      for (const villageName of villages) {
        territories.push({
          id: nextId(),
          name: villageName,
          level: "village",
          code: null,
          parent: { id: taluka.id, name: taluka.name, level: taluka.level },
          district: districtName,
        });
      }
    }
  }

  // Last, so every id above stays as it was.
  territories.push({
    id: nextId(),
    name: MOCK_OTHER_STATE.name,
    level: "state",
    code: MOCK_OTHER_STATE.code,
    parent: null,
    district: null,
  });

  return territories;
}

/**
 * Gujarat, its 33 districts, and talukas and villages for the three worked districts; and
 * Uttar Pradesh on its own, for a second state's subsidy scheme.
 */
export const MOCK_TERRITORIES: readonly MockTerritory[] = buildTerritories();

export function findMockTerritory(id: string): MockTerritory | undefined {
  return MOCK_TERRITORIES.find((territory) => territory.id === id);
}

/** The office a lead in this territory routes to, or null when none covers it. */
export function mockOfficeFor(territory: MockTerritory): { id: string; name: string } | null {
  if (territory.district === MOCK_UNCOVERED_DISTRICT) {
    return null;
  }
  const name =
    (territory.district === null ? undefined : MOCK_DISTRICT_OFFICES[territory.district]) ??
    MOCK_STATE_OFFICE;
  const offices = [MOCK_STATE_OFFICE, ...Object.values(MOCK_DISTRICT_OFFICES)];
  return { id: mockUuid(MOCK_ID_SPACE.orgUnit, offices.indexOf(name) + 1), name };
}

/** The territory as a lead carries it: `{ id, name, level }`. */
export function toTerritoryRef(territory: MockTerritory): {
  id: string;
  name: string;
  level: string;
} {
  return { id: territory.id, name: territory.name, level: territory.level };
}

/** The territory and every territory above it, nearest first: village → taluka → district → state. */
export function mockTerritoryLineage(id: string): MockTerritory[] {
  const lineage: MockTerritory[] = [];
  let current = findMockTerritory(id);
  while (current !== undefined) {
    lineage.push(current);
    current = current.parent ? findMockTerritory(current.parent.id) : undefined;
  }
  return lineage;
}
