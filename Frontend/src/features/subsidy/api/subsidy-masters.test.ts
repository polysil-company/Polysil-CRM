import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockStateTerritoryId } from "@/mocks/data/subsidy-schemes";
import { mockDb, resetMockDb } from "@/mocks/db";

import { getLeadScheme, listApplications, listStageDefs } from "./subsidy-applications.api";
import {
  createMatrix,
  listMaster,
  listUnitCostMatrices,
  reviseMaster,
} from "./subsidy-masters.api";
import {
  createScheme,
  getScheme,
  listSchemes,
  patchScheme,
  renameStage,
} from "./subsidy-schemes.api";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function upState(): string {
  const id = mockStateTerritoryId("UP");
  if (id === null) throw new Error("No Uttar Pradesh in the mock");
  return id;
}

async function createUp(): Promise<void> {
  await createScheme({
    body: {
      code: "upmis",
      name: "UP Micro Irrigation",
      state_territory_id: upState(),
      template: "GGRC",
      systems: ["drip", "sprinkler"],
    },
    idempotencyKey: "up-1",
  });
}

describe("[SUBS-012] Subsidy masters", () => {
  beforeEach(reset);
  afterEach(reset);

  it("revises a row from today: the old row ends, the new one starts", async () => {
    const today = todayInIndia();
    const [first] = await listMaster("categories", "GGRC", null);
    if (first === undefined) throw new Error("No category in the seed");
    const { id: _id, effective_from: _from, effective_to: _to, ...row } = first;
    const result = await reviseMaster({
      kind: "categories",
      body: { scheme: "GGRC", effective_from: today, rows: [{ ...row, pct: "55" }] },
      idempotencyKey: "rev-1",
    });
    expect(result).toEqual({ closed: 1, inserted: 1, effectiveFrom: today });
    const after = await listMaster("categories", "GGRC", today);
    expect(
      after.find((row) => row.code === first.code && row.system_type === first.system_type)?.pct,
    ).toBe("55");
  });

  it("refuses a backdated revision and a second one on the same day", async () => {
    const [first] = await listMaster("crop-spacings", "GGRC", null);
    if (first === undefined) throw new Error("No crop spacing in the seed");
    const row = { crop: first.crop, standard_spacing: "2.00", sort_order: first.sort_order };
    await expect(
      reviseMaster({
        kind: "crop-spacings",
        body: { scheme: "GGRC", effective_from: "2020-01-01", rows: [row] },
        idempotencyKey: "rev-2",
      }),
    ).rejects.toMatchObject({ status: 422, code: "revision_in_past" });
    const today = todayInIndia();
    await reviseMaster({
      kind: "crop-spacings",
      body: { scheme: "GGRC", effective_from: today, rows: [row] },
      idempotencyKey: "rev-3",
    });
    await expect(
      reviseMaster({
        kind: "crop-spacings",
        body: { scheme: "GGRC", effective_from: today, rows: [row] },
        idempotencyKey: "rev-4",
      }),
    ).rejects.toMatchObject({ status: 409, code: "revision_on_start_date" });
  });

  it("keeps each scheme's masters apart", async () => {
    await createUp();
    expect(await listMaster("categories", "UPMIS", null)).toEqual([]);
    expect((await listMaster("categories", "GGRC", null)).length).toBeGreaterThan(0);
    await expect(listMaster("categories", "NOPE", null)).rejects.toMatchObject({ status: 404 });
  });
});

describe("[SUBS-013] Subsidy matrices", () => {
  beforeEach(reset);
  afterEach(reset);

  it("starts a scheme's first matrix from blank", async () => {
    await createUp();
    const today = todayInIndia();
    await createMatrix({
      request: {
        kind: "unit-cost-matrices",
        body: {
          scheme: "UPMIS",
          system_type: "drip",
          variant: "regular",
          dimensionality: 2,
          effective_from: today,
          source: "UP unit cost table",
          unit_cost_cells: [
            { lateral_spacing: "1.20", area_breakpoint: "1.000", unit_cost: "100000" },
          ],
        },
      },
      idempotencyKey: "mx-1",
    });
    const matrices = await listUnitCostMatrices("UPMIS", today);
    expect(matrices).toHaveLength(1);
    const detail = await getScheme("UPMIS", today);
    expect(detail.systems.find((row) => row.systemType === "drip")?.missing).not.toContain(
      "unit_cost_matrix:regular",
    );
  });
});

describe("[SUBS-014] Subsidy schemes", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists GGRC linked to Gujarat, ready, with its applications", async () => {
    const [ggrc] = await listSchemes();
    expect(ggrc).toMatchObject({ code: "GGRC", active: true, ready: true });
    expect(ggrc?.state?.name).toBe("Gujarat");
    const applications = await listApplications({
      status: null,
      stage: null,
      q: "",
      leadId: null,
      cursor: null,
    });
    expect(ggrc?.applications).toBeGreaterThanOrEqual(applications.items.length);
  });

  it("sets up a state's scheme: upper-case code, template's stages, no figures, not ready", async () => {
    await createUp();
    const detail = await getScheme("UPMIS", null);
    expect(detail.ready).toBe(false);
    expect(detail.systems.map((row) => row.systemType)).toEqual(["drip", "sprinkler"]);
    expect(detail.systems[0]?.missing.slice(0, 3)).toEqual([
      "unit_cost_matrix:regular",
      "unit_cost_matrix:seven_year",
      "categories",
    ]);
    expect(detail.stages.length).toBeGreaterThan(0);
  });

  it("refuses a taken code, a covered state and a system the template lacks", async () => {
    await createUp();
    const body = {
      code: "UPMIS",
      name: "Again",
      state_territory_id: upState(),
      template: "GGRC",
      systems: null,
    };
    await expect(createScheme({ body, idempotencyKey: "c-1" })).rejects.toMatchObject({
      status: 409,
      code: "code_taken",
    });
    await expect(
      createScheme({ body: { ...body, code: "UP2" }, idempotencyKey: "c-2" }),
    ).rejects.toMatchObject({ status: 409, code: "state_has_scheme" });
    mockDb.subsidySchemes = mockDb.subsidySchemes.filter((scheme) => scheme.code !== "UPMIS");
    await expect(
      createScheme({ body: { ...body, code: "UP3", template: "NOPE" }, idempotencyKey: "c-3" }),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("links an unlinked scheme once, and refuses a new one until then", async () => {
    const ggrc = mockDb.subsidySchemes[0];
    if (ggrc === undefined) throw new Error("No GGRC");
    const gujarat = ggrc.state_territory_id;
    ggrc.state_territory_id = null;
    await expect(createUp()).rejects.toMatchObject({ status: 409, code: "unlinked_scheme_exists" });
    if (gujarat === null) throw new Error("GGRC had no state");
    await patchScheme({
      code: "GGRC",
      body: { state_territory_id: gujarat },
      idempotencyKey: "l-1",
    });
    await expect(
      patchScheme({ code: "GGRC", body: { state_territory_id: upState() }, idempotencyKey: "l-2" }),
    ).rejects.toMatchObject({ status: 409, code: "state_fixed" });
    await createUp();
  });

  it("renames a stage for the scheme's applications, and a switched-off scheme leaves its leads without one", async () => {
    const [stage] = await listStageDefs("GGRC");
    if (stage === undefined) throw new Error("No stage");
    await renameStage({
      code: "GGRC",
      stageCode: stage.code,
      name: "Inward",
      idempotencyKey: "s-1",
    });
    const [renamed] = await listStageDefs("GGRC");
    expect(renamed?.name).toBe("Inward");

    const lead = mockDb.leads[0];
    if (lead === undefined) throw new Error("No lead");
    expect(await getLeadScheme(lead.id)).toMatchObject({ code: "GGRC", ready: true });
    await patchScheme({ code: "GGRC", body: { is_active: false }, idempotencyKey: "off-1" });
    await expect(getLeadScheme(lead.id)).rejects.toMatchObject({
      status: 422,
      code: "no_scheme_for_state",
    });
  });
});
