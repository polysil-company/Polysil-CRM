import type { LookupItem } from "@/features/lookups/api/lookups.schemas";

/**
 * "agri_fair" → "Agri fair". Stands in for a lookup's name while the list loads, or for a
 * code the list no longer has, so a cell never shows a raw code or nothing at all.
 */
export function humanizeCode(code: string): string {
  const words = code.replace(/[_-]+/g, " ").trim();
  if (words === "") {
    return code;
  }
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

/** The display name for a code, from a loaded lookup list when there is one. */
export function findLookupName(items: readonly LookupItem[] | undefined, code: string): string {
  return items?.find((item) => item.code === code)?.name ?? humanizeCode(code);
}

/** The name of the row with this id — events and records that store the id, not the code. */
export function findLookupNameById(
  items: readonly LookupItem[] | undefined,
  id: string,
): string | null {
  return items?.find((item) => item.id === id)?.name ?? null;
}

const TERRITORY_LEVEL_LABELS: Readonly<Record<string, string>> = {
  state: "State",
  district: "District",
  taluka: "Taluka",
  village: "Village",
};

/** "taluka" → "Taluka". Unknown levels still read well. */
export function territoryLevelLabel(level: string): string {
  return TERRITORY_LEVEL_LABELS[level] ?? humanizeCode(level);
}

/** "Gondal · Taluka" — a territory named with its level, for places without its parent. */
export function formatTerritory(territory: { name: string; level: string }): string {
  return `${territory.name} · ${territoryLevelLabel(territory.level)}`;
}
