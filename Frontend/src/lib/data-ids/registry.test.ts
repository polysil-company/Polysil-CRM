import { describe, expect, it } from "vitest";

import { DATA_ID_DOMAINS, DATA_ID_PATTERN, DATA_IDS, isDataId } from "@/lib/data-ids";

describe("[OBS-002] Data ID registry", () => {
  const entries = Object.entries(DATA_IDS);

  it("uses the DOMAIN-NNN format with a registered domain matching the entry", () => {
    for (const [id, definition] of entries) {
      const match = DATA_ID_PATTERN.exec(id);
      expect(match, id).not.toBeNull();
      expect(match?.[1], id).toBe(definition.domain);
      expect(Object.keys(DATA_ID_DOMAINS), id).toContain(definition.domain);
    }
  });

  it("describes endpoints as METHOD /path", () => {
    for (const [id, definition] of entries) {
      for (const endpoint of "endpoints" in definition ? definition.endpoints : []) {
        expect(endpoint, id).toMatch(/^(GET|POST|PUT|PATCH|DELETE) \/\S*$/);
      }
    }
  });

  it("has non-empty titles", () => {
    for (const [id, definition] of entries) {
      expect(definition.title.length, id).toBeGreaterThan(5);
    }
  });

  it("guards unknown IDs", () => {
    expect(isDataId("LEAD-001")).toBe(true);
    expect(isDataId("LEAD-999")).toBe(false);
    expect(isDataId(42)).toBe(false);
  });
});
