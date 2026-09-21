import { DATA_IDS, type DataId } from "./registry";

export { DATA_ID_DOMAINS, DATA_ID_PATTERN, DATA_IDS, type DataId } from "./registry";

/** Type guard: is `value` a registered Data ID? */
export function isDataId(value: unknown): value is DataId {
  return typeof value === "string" && Object.hasOwn(DATA_IDS, value);
}
