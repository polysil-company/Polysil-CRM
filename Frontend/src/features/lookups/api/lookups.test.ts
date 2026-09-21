import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { server } from "@/mocks/node";

import { listLookup, searchTerritories } from "./lookups.api";

describe("[MSTR-002] listLookup", () => {
  it("returns the backend's rows as codes and names", async () => {
    const systems = await listLookup("mis-systems");

    expect(systems.map((system) => system.code)).toEqual([
      "drip",
      "mini_sprinkler",
      "sprinkler",
      "automation",
      "other",
    ]);
    expect(systems[0]).toMatchObject({ code: "drip", name: "Drip", isActive: true });
  });

  it("keeps inactive rows, marked, and treats a missing flag as active", async () => {
    server.use(
      http.get(buildApiUrl("/lookups/lead-sources"), () =>
        HttpResponse.json({
          data: [
            { id: "1", code: "website", name: "Website" },
            { id: "2", code: "fax", name: "Fax", is_active: false },
          ],
        }),
      ),
    );

    const sources = await listLookup("lead-sources");

    expect(sources).toEqual([
      { id: "1", code: "website", name: "Website", isActive: true },
      { id: "2", code: "fax", name: "Fax", isActive: false },
    ]);
  });
});

describe("[MSTR-002] searchTerritories", () => {
  it("lists districts to start from", async () => {
    const districts = await searchTerritories({ q: "", level: "district", limit: 50 });

    expect(districts).toHaveLength(33);
    expect(districts.every((territory) => territory.level === "district")).toBe(true);
    expect(districts[0]?.parent).toMatchObject({ name: "Gujarat", level: "state" });
  });

  it("finds a place by part of its name at any level, with the place above it", async () => {
    const results = await searchTerritories({ q: "gond", level: null, limit: 20 });

    expect(results).toContainEqual(
      expect.objectContaining({
        name: "Gondal",
        level: "taluka",
        parent: expect.objectContaining({ name: "Rajkot" }),
      }),
    );
  });

  it("fails with the Data ID on the error", async () => {
    server.use(
      http.get(buildApiUrl("/lookups/territories"), () =>
        HttpResponse.json({ error: { code: "boom", message: "boom" } }, { status: 500 }),
      ),
    );

    await expect(searchTerritories({ q: "x", level: null, limit: 20 })).rejects.toMatchObject({
      status: 500,
      dataId: "MSTR-002",
    });
  });
});
