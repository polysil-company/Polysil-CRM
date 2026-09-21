import { describe, expect, it } from "vitest";

import {
  findLookupName,
  formatTerritory,
  humanizeCode,
  territoryLevelLabel,
} from "./lookup-labels";

describe("[MSTR-002] lookup labels", () => {
  it("names a code from the loaded list", () => {
    const items = [{ id: "1", code: "agri_fair", name: "Agri Fair", isActive: true }];

    expect(findLookupName(items, "agri_fair")).toBe("Agri Fair");
  });

  it("falls back to a readable form of the code while the list loads or when it lacks the code", () => {
    expect(findLookupName(undefined, "farmer_meeting")).toBe("Farmer meeting");
    expect(findLookupName([], "qr-code")).toBe("Qr code");
    expect(humanizeCode("___")).toBe("___");
  });

  it("names territory levels, including ones it does not know", () => {
    expect(territoryLevelLabel("taluka")).toBe("Taluka");
    expect(territoryLevelLabel("gram_panchayat")).toBe("Gram panchayat");
    expect(formatTerritory({ name: "Gondal", level: "taluka" })).toBe("Gondal · Taluka");
  });
});
