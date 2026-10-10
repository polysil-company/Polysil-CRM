import type { MissingTable } from "@/features/subsidy/api/subsidy-schemes.schemas";

/**
 * SUBS-014 · A readiness `missing` item in words, and the masters table that fills it
 * (handover `subsidy-schemes-contract.md`, "Reading missing"). An item the screen doesn't know
 * shows as the backend sent it, with no table.
 */
export function readMissing(item: string): {
  readonly text: string;
  readonly table: MissingTable | null;
} {
  const [head, ...rest] = item.split(":");
  const detail = rest.join(":");
  switch (head) {
    case "unit_cost_matrix":
      return {
        text: `The ${detail === "seven_year" ? "seven-year" : "regular"} unit-cost matrix`,
        table: "unit-costs",
      };
    case "quantity_matrix":
      return {
        text: detail === "" ? "The quantity matrix" : `The quantity matrix's ${detail} row`,
        table: "quantities",
      };
    case "categories":
      return { text: "The farmer categories", table: "categories" };
    case "crop_spacings":
      return { text: "The crop spacings", table: "crop-spacings" };
    case "parameters":
      return { text: `The ${detail} parameter`, table: "parameters" };
    case "component_rate":
      return { text: `The ${rest.join(" ")} rate`, table: "component-rates" };
    case "stages":
      return { text: "No active stage: contact support", table: null };
    default:
      return { text: item, table: null };
  }
}
