import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";

import {
  calculateSubsidy,
  getSubsidyConfig,
  listSubsidyCategories,
  listSubsidyCrops,
} from "./subsidy.api";
import type { CalculateRequest } from "./subsidy.schemas";

const DRIP: CalculateRequest = {
  system_type: "drip",
  crops: [
    {
      crop: "Pomegranate",
      inter_crop: null,
      area: "1.000",
      crop_spacing: "4.5 x 3",
      lateral_spacing: "4.00",
      lines: [{ description: "16 mm lateral", uom: "Mtr.", rate: "12.50", qty: "2200" }],
    },
  ],
  head_lines: [{ description: "Screen filter", uom: "No.", rate: "6500.00", qty: "1" }],
  installation_rate_per_ha: "4000",
};

describe("[SUBS-003] Subsidy lookups", () => {
  afterEach(() => {
    writeMockRole("admin");
  });

  it("reads what each system accepts, the crops and the categories", async () => {
    writeMockRole("employee");
    const config = await getSubsidyConfig(null);
    expect(config.systems.map((system) => system.systemType)).toEqual([
      "drip",
      "mini_sprinkler",
      "sprinkler",
    ]);
    const sprinkler = config.systems.find((system) => system.systemType === "sprinkler");
    expect(sprinkler).toMatchObject({ hasHeadUnit: false, supportsGroup: false, cropCountMax: 1 });
    expect(sprinkler?.sprinklerAreas).toContain("2.010");
    expect(config.parameters.insurance_rate).toBe("0.0028");

    const crops = await listSubsidyCrops(null);
    expect(crops).toContainEqual({ crop: "Mango", standardSpacing: "5.00" });

    const categories = await listSubsidyCategories("mini_sprinkler", null);
    expect(categories).toHaveLength(8);
    expect(categories[0]).toMatchObject({ code: "small_farmer", gsdmaPct: "10" });
  });

  it("refuses a dealer: portal users have no subsidy", async () => {
    writeMockRole("dealer");
    await expect(getSubsidyConfig(null)).rejects.toMatchObject({ status: 403 });
  });
});

describe("[SUBS-002] Subsidy calculation", () => {
  afterEach(() => {
    writeMockRole("admin");
  });

  it("returns the blocks, the unit cost and all eight categories as decimal strings", async () => {
    const result = await calculateSubsidy(DRIP);
    expect(result.systemType).toBe("drip");
    expect(result.crops).toHaveLength(1);
    const crop = result.crops[0];
    expect(crop?.spacing).toEqual({ designed: "4.00", standard: "4.50", forSubsidy: "4.50" });
    expect(crop?.categories).toHaveLength(8);
    expect(crop?.unitCostForCap).toMatch(/^\d+\.\d{4}$/);
    expect(result.total.total_incl_gst).toMatch(/^\d+\.\d{2}$/);
    expect(result.sprinkler).toBeNull();
  });

  it("lets the inter-crop set the standard spacing", async () => {
    const result = await calculateSubsidy({
      ...DRIP,
      crops: DRIP.crops.map((crop) => ({ ...crop, inter_crop: "Banana", lateral_spacing: "1.20" })),
    });
    expect(result.crops[0]?.spacing.standard).toBe("1.80");
  });

  it("names the field a refusal is about", async () => {
    await expect(
      calculateSubsidy({
        ...DRIP,
        crops: DRIP.crops.map((crop) => ({ ...crop, crop: "Saffron" })),
        group_total_area: "0.500",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: {
        fields: {
          "crops[0].crop": "not in the crop table",
          group_total_area: "must be at least the sum of the crop areas",
        },
      },
    });
  });

  it("derives Sprinkler's lines and refuses an area the table doesn't hold", async () => {
    const sprinkler: CalculateRequest = {
      system_type: "sprinkler",
      crops: [
        {
          crop: "Groundnut",
          inter_crop: null,
          area: "1.200",
          crop_spacing: "",
          lateral_spacing: "12.00",
          lines: [],
        },
      ],
      nozzle: "brass",
    };
    const result = await calculateSubsidy(sprinkler);
    expect(result.sprinkler).toMatchObject({ pipeSizeMm: 75, nozzle: "brass" });
    expect(result.crops[0]?.warnings[0]).toMatch(/^spacing_outside_table: /);

    await expect(
      calculateSubsidy({
        ...sprinkler,
        crops: sprinkler.crops.map((crop) => ({ ...crop, area: "1.300" })),
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { "crops[0].area": expect.any(String) } },
    });
  });
});
